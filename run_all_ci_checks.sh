poetry run isort --profile black .
poetry run black .
poetry run autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive .
poetry run mypy
