use std::io::ErrorKind;
use std::str;

use anyhow::{anyhow, Context, Result};
use async_process::{Command, Output};
use async_std::fs;
use async_std::fs::read_to_string;
use async_std::path::PathBuf;
use itertools::Itertools;
use serde::{Deserialize, Serialize};
use serde_aux::serde_introspection::serde_introspect;
use thiserror::Error;
use urlencoding::encode;

use super::cache::Cache;

#[derive(Error, Debug)]
pub enum YtDlError {
    #[error("yt-dlp not found")]
    YtDlpNotFound,
    #[error("YouTube item not found")]
    ItemNotFound,
    #[error("yt-dlp exited with an error: {}", .0.status)]
    YtDlpOutputError(Output),
    #[error(transparent)]
    Other(#[from] anyhow::Error),
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct Thumbnail {
    pub url: String,
    pub width: u16,
    pub height: u16,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct Channel {
    pub channel: String,
    pub description: String,
    pub thumbnails: Vec<Thumbnail>,
    pub webpage_url: String,
    #[serde(default)]
    pub videos_url: String,
    pub epoch: u64,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct Video {
    pub id: String,
    pub title: String,
    pub description: String,
    pub upload_date: String,
    pub uploader: String,
    #[serde(rename = "duration_string")]
    pub duration: String,
}

pub struct YtDl<'a> {
    pub ytdlp_path: String,
    pub cache: &'a Cache,
}

impl<'a> YtDl<'a> {
    pub fn new(cache: &'a Cache) -> Self {
        Self {
            ytdlp_path: "yt-dlp".to_string(),
            cache,
        }
    }

    fn get_channel_url(channel_name: &str, page: &str) -> String {
        format!(
            "https://www.youtube.com/c/{}/{}",
            encode(channel_name),
            encode(page)
        )
    }

    fn get_user_url(channel_name: &str, page: &str) -> String {
        format!(
            "https://www.youtube.com/user/{}/{}",
            encode(channel_name),
            encode(page)
        )
    }

    pub async fn run(&self, args: &[&str]) -> Result<Output, YtDlError> {
        let output = Command::new(&self.ytdlp_path)
            .args(args)
            .output()
            .await
            .map_err(|e| match e.kind() {
                ErrorKind::NotFound => YtDlError::YtDlpNotFound,
                _ => YtDlError::Other(anyhow!(e)),
            })?;

        if !output.status.success() {
            return Err(YtDlError::YtDlpOutputError(output));
        }

        Ok(output)
    }

    fn map_not_found(err: YtDlError, not_found_str: &str) -> YtDlError {
        match err {
            YtDlError::YtDlpOutputError(ref output) => {
                if String::from_utf8_lossy(&output.stderr).contains(not_found_str) {
                    YtDlError::ItemNotFound
                } else {
                    log::error!("yt-dlp output error: {}", err);
                    err
                }
            }
            _ => {
                log::error!("Error running yt-dlp: {}", err);
                err
            }
        }
    }

    async fn run_get_channel_info(&self, url: &str) -> Result<Output, YtDlError> {
        log::debug!("run_get_channel_info({})", url);
        self.run(&["-J", url])
            .await
            .map_err(|e| YtDl::map_not_found(e, "HTTPError 404"))
    }

    pub async fn get_channel_info(&self, channel_name: &str) -> Result<Channel, YtDlError> {
        log::debug!("get_channel_info");

        let channel_about_url = YtDl::get_channel_url(channel_name, "about");
        let user_about_url = YtDl::get_user_url(channel_name, "about");

        let mut vids_url = YtDl::get_channel_url(channel_name, "videos");
        let output_result = self.run_get_channel_info(&channel_about_url).await;
        let output = match output_result {
            Ok(o) => Ok(o),
            Err(e) => match e {
                // Try user url if channel url didn't work
                YtDlError::ItemNotFound => {
                    vids_url = YtDl::get_user_url(channel_name, "videos");
                    self.run_get_channel_info(&user_about_url).await
                }
                _ => {
                    log::error!("Bad output_result: {}", e);
                    Err(e)
                }
            },
        }?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let mut channel: Channel =
            serde_json::from_str(&stdout).context("failed to parse ytdl output")?;
        channel.videos_url = vids_url;

        Ok(channel)
    }

    pub async fn get_channel_videos(
        &self,
        channel_info: &Channel,
        limit: Option<i64>,
    ) -> Result<Vec<Video>, YtDlError> {
        log::debug!("get_channel_videos");

        let limit = limit.unwrap_or(5);

        let cache_path = self
            .cache
            .get_path(vec!["playlist", &channel_info.channel], None)
            .await?;

        let cached = read_to_string(&cache_path)
            .await
            .context("cache read failed")?;
        let output = if cached.is_empty() {
            // Prepare a template for ytdl requesting just the data we need (it's faster that way)
            let field_template = String::from("{")
                + &serde_introspect::<Video>()
                    .iter() // struct field names
                    .map(|f| format!("\"{}\":%({})j", f, f))
                    .join(",")
                + "}";

            let out = self
                .run(&[
                    "-S",
                    "ext",
                    "--print",
                    &field_template,
                    "--playlist-end",
                    &limit.to_string(),
                    &channel_info.videos_url,
                ])
                .await?;
            let out_str = String::from_utf8_lossy(&out.stdout).into();

            if let Err(e) = fs::write(&cache_path, &out_str).await {
                log::error!("Failed to save cache: {}", e);
            }

            out_str
        } else {
            cached
        };

        let vids = output
            .lines()
            .map(|l| serde_json::from_str(l).context("couldn't parse ytdl output"))
            .collect::<Result<_>>()?;

        Ok(vids)
    }

    pub async fn download_video(&self, id: &str, output: &PathBuf) -> Result<(), YtDlError> {
        let vid_url = format!("https://www.youtube.com/watch?v={}", encode(id));

        self.run(&[
            "--sponsorblock-remove",
            "all",
            "-S",
            "ext,height:720",
            "-o",
            output.to_str().ok_or_else(|| anyhow!("bad output path"))?,
            &vid_url,
        ])
        .await
        .map_err(|e| YtDl::map_not_found(e, "Video unavailable"))?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_get_channel_videos() -> Result<()> {
        let cache = Cache::new()?;
        let yt = YtDl::new(&cache);
        let info = yt.get_channel_info("techmoan").await?;
        let vids = yt.get_channel_videos(&info, None).await?;

        assert!(!vids.is_empty());

        Ok(())
    }

    #[tokio::test]
    async fn test_get_channel_info() -> Result<()> {
        let cache = Cache::new()?;
        let yt = YtDl::new(&cache);
        let info = yt.get_channel_info("techmoan").await?;

        assert_eq!(info.channel, "Techmoan");

        Ok(())
    }

    #[tokio::test]
    async fn test_channel_info_not_found() -> Result<()> {
        let cache = Cache::new()?;
        let yt = YtDl::new(&cache);

        match yt
            .get_channel_info("thischannelhopefullydoesnotexist")
            .await
        {
            Ok(_) => panic!("should have returned not found"),
            Err(e) => match e {
                YtDlError::ItemNotFound => Ok(()),
                _ => panic!("should have returned not found"),
            },
        }
    }
}
