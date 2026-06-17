def main() -> None:
    """Console entry point: run the musikbox HTTP server (musikbox-server)."""
    import uvicorn

    from musikbox.bootstrap import bootstrap_server
    from musikbox.server.app import create_api

    services = bootstrap_server()
    api = create_api(services)
    uvicorn.run(api, host=services.config.server_host, port=services.config.server_port)


if __name__ == "__main__":
    main()
