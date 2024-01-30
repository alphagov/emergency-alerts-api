# GOV.UK Emergency Alerts API

Contains:
- the public-facing REST API for GOV.UK Emergency Alerts, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/emergency-alerts-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up to run the API Server locally

### Local Development Environment Setup
Ensure that you have first followed all of the local development environment setup steps, that can be found [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/3211265/Mac+Setup), before attempting to run the API Server locally.

### Python version

You can find instructions on setting the correct Python version [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/192217089/Setting+up+Local+Development+Environment#Setting-Python-Version).

### psycopg2

[Follow these instructions on Mac M1 machines](https://github.com/psycopg/psycopg2/issues/1216#issuecomment-1068150544).

### Environment Variables and Hosting

The HOST variable is used to distinguish between running locally and on the hosted infrastructure (i.e. AWS). This variable can therefore take one of the following values:

HOST = [ local | hosted | test ]

"local" indicates that the service will be configured for running on a local machine. "hosted" is intended for use when the service is running on the AWS-hosted infrastructure. "test" provides a special set of configuration values that are used by the unit, integration and functional tests.

The environment variable ENVIRONMENT is used to tell the service which set of config values to take up, and can be set to one of the following values:

ENVIRONMENT = [ local | development | preview | staging | production ]

A value of "local" indicates that the service will be running on the development machine. A value corresponding to any of the others in the above set maps directly to the name of the environment hosted in AWS.

The development environment hosted on AWS will now configure the above variables as follows:
HOST=hosted & ENVIRONMENT=development


### `environment.sh`

The instructions on setting up the `environment.sh` file can be found [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/192217089/Setting+up+Local+Development+Environment#Getting-API-setup).


## Running the Admin and Api services with Postgres

Please refer to the README in the /emergency-alerts-tooling repository, in the /emergency-alerts-tooling/compose folder.


## THE FOLLOWING INSTRUCTIONS ARE DEPRECATED AND SHOULD BE USED FOR HISTORICAL REFERENCE ONLY
(This section will be removed in the future, as the Emergency Alerts app is fully decoupled from Notify)


### Redis

To switch redis on you'll need to install it locally. On a Mac you can do:

```
# assuming you use Homebrew
brew install redis
brew services start redis
```

To use redis caching you need to switch it on with an environment variable:

```
export REDIS_ENABLED=1
```

### Pre-commit

We use [pre-commit](https://pre-commit.com/) to ensure that committed code meets basic standards for formatting, and will make basic fixes for you to save time and aggravation.

Install pre-commit system-wide with, eg `brew install pre-commit`. Then, install the hooks in this repository with `pre-commit install --install-hooks`.

##  To run the application

See [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/192217089/Setting+up+Local+Development+Environment#Run-the-API-Server) for instructions on running the API server locally.

###  Running application with Celery

```

# run the background tasks
make run-celery

# run scheduled tasks (optional)
make run-celery-beat
```

We've had problems running Celery locally due to one of its dependencies: pycurl. Due to the complexity of the issue, we also support running Celery via Docker:

```
# install dependencies, etc.
make bootstrap-with-docker

# run the background tasks
make run-celery-with-docker

# run scheduled tasks
make run-celery-beat-with-docker
```

##  To test the application

See [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/192217089/Setting+up+Local+Development+Environment#Running-the-Unit-Tests) for instructions on running unit tests.

## To run one off tasks

Tasks are run through the `flask` command - run `flask --help` for more information. There are two sections we need to
care about: `flask db` contains alembic migration commands, and `flask command` contains all of our custom commands. For
example, to purge all dynamically generated functional test data, do the following:

Locally
```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

On the server
```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```

All commands and command options have a --help command if you need more information.

## Further documentation

- [Writing public APIs](docs/writing-public-apis.md)
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)
