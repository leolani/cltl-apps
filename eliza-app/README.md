# eliza-app

Repository for the Eliza App.

This repository contains all components of the Eliza app as _git_ submodules and can be used as the
root to execute [build commands](https://github.com/leolani/cltl-build/tree/main/make) that are run on the components.

For a description of the Eliza App see to the [README](app/README.md) there.

## Check-out

To check out all code needed for the Eliza App, clone this repository including all submodules:

        git clone --recurse-submodules -j8 https://github.com/leolani/eliza-app.git


## Run the application

Checkout the repository as described in [Check-out](#check-out). Then go to the
repository root, build the project, activate the virtual environment for the
Python application and run it. Altogether:

        git clone --recurse-submodules -j8 https://github.com/leolani/eliza-app.git
        cd eliza-app
        make build
        make build
        cd app
        source venv/bin/active
        cd py-app
        python app.py


## Development

Follow the instructions in [cltl-combot](https://github.com/leolani/cltl-combot).
