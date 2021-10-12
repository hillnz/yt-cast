#[macro_use] extern crate rocket;

use anyhow::{anyhow, Result};
use dotenv::dotenv;
use rocket::fs::NamedFile;
use rocket::response::content::Xml;
use rocket::http::Status;
use rocket::serde::Deserialize;
use rocket::State;

mod podcast_proxy;
mod ytdl;
mod cache;

use podcast_proxy::{PodcastProxy, PodcastError};
use cache::Cache;

#[derive(Deserialize)]
struct AppConfig {
    base_url: String,
    channel_whitelist: Vec<String>
}

struct AppState {
    proxy: PodcastProxy
}


#[get("/feed/<channel_name>")]
async fn get_feed(config: &State<AppConfig>, state: &State<AppState>, channel_name: &str) -> Result<Xml<String>, Status> {
    
    if ! config.channel_whitelist.contains(&channel_name.to_string()) {
        return Err(Status::NotFound);
    }

    match state.proxy.get_feed(&format!("{}/media/", config.base_url), channel_name).await {
        Ok(s) => Ok(Xml(s)),
        Err(e) => match e {
            PodcastError::NotFound => Err(Status::NotFound),
            _ => {
                log::error!("{}", anyhow!(e));
                Err(Status::InternalServerError)
            }
        }
    }

}


#[get("/media/<id>")]
async fn get_media(state: &State<AppState>, id: &str) -> Result<NamedFile, Status> {
    let downloaded_path = state.proxy.get_video(id).await
        .map_err(|e| match e {
            PodcastError::NotFound => Status::NotFound,
            _ => Status::InternalServerError
        })?;

    let file = NamedFile::open(downloaded_path).await
        .map_err(|_| Status::InternalServerError)?;

    Ok(file)
}


#[catch(404)]
async fn not_found() -> String {
    "".to_string()
}


#[rocket::main]
async fn main() -> Result<()> {
    dotenv().ok();

    let cache = Cache::new()?;
    
    let state = AppState {
        proxy: PodcastProxy { 
            cache
        }
    };

    let rocket = rocket::build();

    let config: AppConfig = rocket.figment().extract()?;

    rocket
        .mount("/", routes![
            get_feed,
            get_media
        ])
        .manage(state)
        .manage(config)
        .register("/", catchers![
            not_found
        ])
        .launch()
        .await?;

    Ok(())
}
