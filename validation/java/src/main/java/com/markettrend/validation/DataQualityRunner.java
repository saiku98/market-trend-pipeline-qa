package com.markettrend.validation;

import java.sql.SQLException;

/**
 * Standalone CI entry point: runs the Java-side data-quality checks against
 * the warehouse and exits non-zero if any of them fail. Intended to run
 * alongside (not instead of) `validation/python/checks.py` in the pipeline's
 * CI workflow.
 */
public final class DataQualityRunner {

    private DataQualityRunner() {
    }

    public static void main(String[] args) throws SQLException {
        if (args.length != 1) {
            System.err.println("usage: DataQualityRunner <path-to-sqlite-db>");
            System.exit(2);
        }
        String dbPath = args[0];
        boolean allPassed = true;

        try (WarehouseClient client = new WarehouseClient(dbPath)) {
            allPassed &= report("raw_prices row count > 0", client.countRows("raw_prices") > 0);
            allPassed &= report("no invalid prices", client.countInvalidPrices() == 0);
            allPassed &= report("no duplicate price ticks", client.countDuplicatePriceTicks() == 0);
            allPassed &= report("no invalid trend labels", client.countInvalidTrendLabels() == 0);
        }

        if (!allPassed) {
            System.err.println("\nOne or more Java-side data-quality checks failed.");
            System.exit(1);
        }
        System.out.println("\nAll Java-side data-quality checks passed.");
    }

    private static boolean report(String checkName, boolean passed) {
        System.out.println("[" + (passed ? "PASS" : "FAIL") + "] " + checkName);
        return passed;
    }
}
