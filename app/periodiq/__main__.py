import periodiq

# We can't use the Periodiq CLI as then the import order is wrong for OpenTelemetry
# (our instrumentation can't override the __main__ module from Periodiq's CLI)

if "__main__" == __name__:
    periodiq.entrypoint()
