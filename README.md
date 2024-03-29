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

##  To test the application

See [here](https://gds-ea.atlassian.net/wiki/spaces/EA/pages/192217089/Setting+up+Local+Development+Environment#Running-the-Unit-Tests) for instructions on running unit tests.

## Running the Admin and Api services with Postgres

Please refer to the README in the /emergency-alerts-tooling repository, in the /emergency-alerts-tooling/compose folder.

## Further documentation

- [Writing public APIs](docs/writing-public-apis.md)
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)
