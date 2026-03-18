import logging

import periodiq

# We can't use the Periodiq CLI as then the import order is wrong for OpenTelemetry
# (our instrumentation can't override the __main__ module from Periodiq's CLI)

if "__main__" == __name__:
    # Hack: The periodiq entrypoint sets up a logger but our app does that
    # Let's just patch that out
    def noop(**kwargs):
        pass

    logging.basicConfig = noop

    periodiq.entrypoint()
