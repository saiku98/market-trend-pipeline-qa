# Java validation module

Independent, JDBC-based data-quality checks against the SQLite warehouse.
Deliberately kept separate from `validation/python/checks.py`: the two
suites check overlapping invariants using different tooling, so a logic bug
in one is unlikely to be reproduced in the other.

```bash
mvn -f validation/java/pom.xml test
mvn -f validation/java/pom.xml package
java -jar validation/java/target/market-trend-validation.jar ../../data/market_data.db
```
