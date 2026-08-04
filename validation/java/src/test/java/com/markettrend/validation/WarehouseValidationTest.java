package com.markettrend.validation;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WarehouseValidationTest {

    private Path dbFile;
    private WarehouseClient client;

    @BeforeEach
    void setUp(@TempDir Path tempDir) throws SQLException, IOException {
        dbFile = tempDir.resolve("test.db");
        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbFile);
             Statement stmt = conn.createStatement()) {
            stmt.execute("CREATE TABLE raw_prices (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    + "asset TEXT NOT NULL, price_usd REAL NOT NULL, observed_at TEXT NOT NULL)");
            stmt.execute("CREATE TABLE trend_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    + "asset TEXT NOT NULL, window_end TEXT NOT NULL, window_size INTEGER NOT NULL, "
                    + "moving_avg_usd REAL NOT NULL, volatility REAL NOT NULL, momentum REAL NOT NULL, "
                    + "trend_label TEXT NOT NULL)");
        }
        client = new WarehouseClient(dbFile.toString());
    }

    @AfterEach
    void tearDown() throws SQLException {
        client.close();
    }

    private void insertPrice(String asset, double price, String observedAt) throws SQLException {
        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbFile);
             Statement stmt = conn.createStatement()) {
            stmt.execute(String.format(
                    "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES ('%s', %f, '%s')",
                    asset, price, observedAt));
        }
    }

    private void insertTrend(String label) throws SQLException {
        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbFile);
             Statement stmt = conn.createStatement()) {
            stmt.execute(String.format(
                    "INSERT INTO trend_metrics (asset, window_end, window_size, moving_avg_usd, "
                            + "volatility, momentum, trend_label) "
                            + "VALUES ('bitcoin', '2026-08-04T00:00:00', 5, 100.0, 1.0, 0.1, '%s')",
                    label));
        }
    }

    @Test
    void countRows_returnsZeroOnEmptyTable() throws SQLException {
        assertEquals(0, client.countRows("raw_prices"));
    }

    @Test
    void countRows_reflectsInsertedRows() throws SQLException {
        insertPrice("bitcoin", 50000.0, "2026-08-04T00:00:00");
        insertPrice("ethereum", 3000.0, "2026-08-04T00:00:00");
        assertEquals(2, client.countRows("raw_prices"));
    }

    @Test
    void countInvalidPrices_flagsNonPositivePrice() throws SQLException {
        insertPrice("bitcoin", -1.0, "2026-08-04T00:00:00");
        assertEquals(1, client.countInvalidPrices());
    }

    @Test
    void countInvalidPrices_isZeroForCleanData() throws SQLException {
        insertPrice("bitcoin", 50000.0, "2026-08-04T00:00:00");
        assertEquals(0, client.countInvalidPrices());
    }

    @Test
    void countDuplicatePriceTicks_flagsExactDuplicateTimestamp() throws SQLException {
        insertPrice("bitcoin", 50000.0, "2026-08-04T00:00:00");
        insertPrice("bitcoin", 50001.0, "2026-08-04T00:00:00");
        assertEquals(1, client.countDuplicatePriceTicks());
    }

    @Test
    void countInvalidTrendLabels_flagsUnknownLabel() throws SQLException {
        insertTrend("sideways");
        assertEquals(1, client.countInvalidTrendLabels());
    }

    @Test
    void countInvalidTrendLabels_isZeroForKnownLabels() throws SQLException {
        insertTrend("up");
        insertTrend("down");
        insertTrend("flat");
        assertEquals(0, client.countInvalidTrendLabels());
    }

    @Test
    void countRows_rejectsUnknownTableNameSafely() {
        assertEquals(
                IllegalArgumentException.class,
                assertThrowsIllegalArgument(() -> client.countRows("raw_prices; DROP TABLE raw_prices;"))
                        .getClass()
        );
    }

    private interface ThrowingRunnable {
        void run() throws SQLException;
    }

    private static RuntimeException assertThrowsIllegalArgument(ThrowingRunnable runnable) {
        try {
            runnable.run();
        } catch (IllegalArgumentException e) {
            return e;
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
        throw new AssertionError("expected IllegalArgumentException");
    }
}
