FROM rust:1.55.0 AS build

COPY . .

RUN cargo install --path .

FROM debian:11.1-slim

RUN apt-get update && apt-get install -y \
        curl \
        python3

RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

COPY --from=build /usr/local/cargo/bin/yt-cast /usr/local/bin/yt-cast

ENTRYPOINT [ "yt-cast" ]
