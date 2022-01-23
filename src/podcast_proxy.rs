use std::collections::HashMap;

use anyhow::{anyhow, Context, Result};
use async_std::fs;
use async_std::path::PathBuf;
use chrono::{Duration, NaiveDate, TimeZone, Utc};
use rss::extension::itunes::{ITunesChannelExtensionBuilder, ITunesItemExtensionBuilder};
use rss::{ChannelBuilder, EnclosureBuilder, GuidBuilder, ImageBuilder, ItemBuilder};
use thiserror::Error;

use super::cache::Cache;
use super::ytdl;
use super::ytdl::YtDlError;

#[derive(Error, Debug)]
pub enum PodcastError {
    #[error("Not found")]
    NotFound,
    #[error("Youtube error")]
    YoutubeError(#[from] ytdl::YtDlError),
    #[error(transparent)]
    IoError(#[from] std::io::Error),
    #[error(transparent)]
    Other(#[from] anyhow::Error),
}

const ITEM_DELAY: i64 = 3;

pub struct PodcastProxy {
    pub cache: Cache,
}

impl PodcastProxy {
    pub async fn get_feed(
        &self,
        media_base_url: &str,
        channel_name: &str,
    ) -> Result<String, PodcastError> {
        let yt = ytdl::YtDl::new(&self.cache);

        let channel = yt.get_channel_info(channel_name).await.map_err(|e| {
            println!("{:?}", e);
            match e {
                YtDlError::ItemNotFound => PodcastError::NotFound,
                _ => PodcastError::YoutubeError(e),
            }
        })?;
        let vids = yt.get_channel_videos(&channel, None).await?;

        const ARBITRARY_SIZE: u64 = 1_073_741_824;

        let base_url = media_base_url.to_string();

        let mut oldest_date = Utc::now();

        let mut rss_items = vec![];
        for vid in vids {
            let enclosure = EnclosureBuilder::default()
                .url(base_url.clone() + &vid.id)
                .length(ARBITRARY_SIZE.to_string())
                .mime_type("video/mp4")
                .build()
                .map_err(|e| anyhow!(e))?;

            let guid = GuidBuilder::default()
                .value(vid.id.clone())
                .build()
                .map_err(|e| anyhow!(e))?;

            let it_item = ITunesItemExtensionBuilder::default()
                .author(vid.uploader)
                .duration(vid.duration)
                .subtitle(vid.description.clone())
                .summary(vid.description.clone())
                .build()
                .map_err(|e| anyhow!(e))?;

            // Reformat date
            let raw_date =
                NaiveDate::parse_from_str(&vid.upload_date, "%Y%m%d").context("bad upload date")?;
            let date = Utc.from_utc_date(&raw_date).and_hms(0, 0, 0);
            if date < oldest_date {
                oldest_date = date;
            }

            if (Utc::now() - date) < Duration::days(ITEM_DELAY) {
                log::info!(
                    "Ignoring video {} which hasn't been out for {} days yet",
                    vid.id,
                    ITEM_DELAY
                );
                continue;
            }

            let item = ItemBuilder::default()
                .title(vid.title)
                .description(vid.description)
                .enclosure(enclosure)
                .guid(guid)
                .pub_date(date.to_rfc2822())
                .itunes_ext(it_item)
                .build()
                .map_err(|e| anyhow!(e))?;

            rss_items.push(item);
        }

        let rss_itunes = ITunesChannelExtensionBuilder::default()
            .author(channel.channel.clone())
            .block("Yes".to_string())
            // .image(image.clone())
            .subtitle(channel.description.clone())
            .build()
            .map_err(|e| anyhow!(e))?;

        let mut namespaces = HashMap::new();
        namespaces.insert(
            "itunes".into(),
            "http://www.itunes.com/dtds/podcast-1.0.dtd".into(),
        );

        // TODO pub_date, last_build_date RFC822
        let mut rss_channel_builder = ChannelBuilder::default();
        rss_channel_builder
            .title(channel.channel.clone())
            .link(channel.webpage_url)
            .description(channel.description.clone())
            .itunes_ext(rss_itunes)
            .namespaces(namespaces)
            .items(rss_items)
            .pub_date(oldest_date.to_rfc2822());

        if let Some(thumbnail) = channel.thumbnails.first() {
            rss_channel_builder.image(
                ImageBuilder::default()
                    .title(channel.channel.clone())
                    .url(thumbnail.url.clone())
                    .link(thumbnail.url.clone())
                    .width(thumbnail.width.unwrap_or(0).to_string())
                    .height(thumbnail.height.unwrap_or(0).to_string())
                    .build()
                    .map_err(|e| anyhow!(e))?,
            );
        }

        let rss_channel = rss_channel_builder.build().map_err(|e| anyhow!(e))?;

        Ok(rss_channel.to_string())
    }

    pub async fn get_video(&self, video_id: &str) -> Result<PathBuf, PodcastError> {
        let out_path = self
            .cache
            .get_path(vec!["media", video_id], Some("mp4"))
            .await?;

        if out_path.exists().await && fs::metadata(&out_path).await?.len() == 0 {
            fs::remove_file(&out_path).await?;
        }

        if !out_path.exists().await {
            let yt = ytdl::YtDl::new(&self.cache);
            yt.download_video(video_id, &out_path)
                .await
                .map_err(|e| match e {
                    YtDlError::ItemNotFound => PodcastError::NotFound,
                    _ => PodcastError::YoutubeError(e),
                })?;
        }

        Ok(out_path)
    }
}
