import uvicorn

from app import APP_HOST, APP_PORT, app


def main() -> None:
    uvicorn.run(
        app,
        host=APP_HOST,
        port=APP_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
