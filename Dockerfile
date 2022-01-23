FROM --platform=$BUILDPLATFORM jonoh/rust-crossbuild:1.56.1 AS build

WORKDIR /usr/src/app

COPY . .

RUN cargo install --path .

FROM debian:11.2-slim

RUN apt-get update && apt-get install -y \
        ffmpeg \
        python3

ADD https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp /usr/local/bin/yt-dlp
RUN chmod a+rx /usr/local/bin/yt-dlp

COPY --from=build /usr/local/cargo/bin/yt-cast /usr/local/bin/yt-cast

ENTRYPOINT [ "yt-cast" ]
