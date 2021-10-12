FROM rust:1.55.0 AS build

COPY . .

RUN cargo install --path .

FROM debian:11.0-slim

COPY --from=build /usr/local/cargo/bin/yt-cast /usr/local/bin/yt-cast

ENTRYPOINT [ "yt-cast" ]
