# Automated tests

The tests are written in Python and use the `unittest` framework. To run the tests, execute the following command:

```bash
coverage run -m unittest discover -s tests/simulations -s tests/utils
```

Then produce the coverage report with:

```bash
coverage report -m
```

