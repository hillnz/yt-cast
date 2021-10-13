use anyhow::{anyhow, Result};
use async_std::fs;
use async_std::fs::{create_dir_all, remove_dir, File, OpenOptions};
use async_std::io::ErrorKind;
use async_std::path::PathBuf;
use async_std::prelude::*;
use tempfile::TempDir;
use urlencoding::encode;

pub struct Cache {
    dir: TempDir,
    cache_time: u64,
}

impl Cache {
    pub fn new() -> Result<Cache> {
        let c = Cache {
            dir: TempDir::new()?,
            cache_time: 86400,
        };
        Ok(c)
    }

    pub async fn get_path(&self, key: Vec<&str>, ext: Option<&str>) -> Result<PathBuf> {
        let mut p: PathBuf = self.dir.path().into();

        let (last, elements) = key.split_last().ok_or_else(|| anyhow!("empty key"))?;

        for k in elements {
            p.push(encode(k).replace("%", "+"));
            create_dir_all(&p).await?;
        }
        p.push(encode(last).replace("%", "+"));
        if let Some(ext_val) = ext {
            p.set_extension(ext_val);
        }

        // Update file's modification time, or create
        match OpenOptions::new().append(true).open(&p).await {
            Ok(f) => Ok(f),
            Err(e) => match e.kind() {
                ErrorKind::NotFound => File::create(&p).await,
                _ => Err(e),
            },
        }
        .map_err(|e| {
            log::error!("failed to touch/create file: {}", e);
            e
        })?;

        self.clean().await?;

        Ok(p)
    }

    pub async fn clean(&self) -> Result<()> {
        log::debug!("clean()");

        let root: PathBuf = self.dir.path().into();
        let mut dirs = vec![root];

        while let Some(dir) = dirs.pop() {
            let mut empty = true;

            let mut entries = fs::read_dir(&dir).await?;
            while let Some(result) = entries.next().await {
                empty = false;

                let entry = result?;

                let f_type = entry.file_type().await?;
                if f_type.is_dir() {
                    dirs.push(entry.path());
                    continue;
                } else if f_type.is_file() {
                    let modified = entry.metadata().await?.modified()?;
                    if let Ok(time_diff) = modified.elapsed() {
                        if time_diff.as_secs() > self.cache_time {
                            if let Err(e) = fs::remove_file(entry.path()).await {
                                log::warn!("Couldn't remove expired cache file: {}", e);
                            }
                        }
                    }
                }
            }

            if empty {
                remove_dir(dir).await?
            }
        }

        Ok(())
    }
}
