poetry run mypy
poetry run isort --profile black .
poetry run isort --profile black .
git diff --exit-code --quiet || exit 1
poetry run autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive .
git diff --exit-code --quiet || exit 1