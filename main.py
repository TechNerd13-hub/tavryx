from tavryx.app import create_app
from tavryx.config import settings
from tavryx.caspian_adapter import start_caspian_listener
from tavryx.logging_config import configure_logging

configure_logging()
app = create_app()

if __name__ == "__main__":
    import threading
    import uvicorn
    threading.Thread(
        target=start_caspian_listener,
        name="caspian-listener",
        daemon=True,
    ).start()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
