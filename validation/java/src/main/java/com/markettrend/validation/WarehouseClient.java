package com.markettrend.validation;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

/**
 * Thin JDBC wrapper over the market-trend warehouse (SQLite locally,
 * same queries are portable to Postgres in production).
 */
public class WarehouseClient implements AutoCloseable {

    private final Connection connection;

    public WarehouseClient(String dbPath) throws SQLException {
        this.connection = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
    }

    public long countRows(String table) throws SQLException {
        String sql = "SELECT COUNT(*) FROM " + validateTableName(table);
        try (PreparedStatement stmt = connection.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }

    public long countInvalidPrices() throws SQLException {
        String sql = "SELECT COUNT(*) FROM raw_prices WHERE price_usd IS NULL OR price_usd <= 0 "
                + "OR asset IS NULL OR TRIM(asset) = ''";
        try (PreparedStatement stmt = connection.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }

    public long countDuplicatePriceTicks() throws SQLException {
        String sql = "SELECT COUNT(*) FROM ("
                + "  SELECT asset, observed_at FROM raw_prices"
                + "  GROUP BY asset, observed_at HAVING COUNT(*) > 1"
                + ")";
        try (PreparedStatement stmt = connection.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }

    public long countInvalidTrendLabels() throws SQLException {
        String sql = "SELECT COUNT(*) FROM trend_metrics "
                + "WHERE trend_label NOT IN ('up', 'down', 'flat')";
        try (PreparedStatement stmt = connection.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }

    private static String validateTableName(String table) {
        // Guard against SQL injection since table names can't be bind parameters.
        if (!table.matches("[a-zA-Z_][a-zA-Z0-9_]*")) {
            throw new IllegalArgumentException("invalid table name: " + table);
        }
        return table;
    }

    @Override
    public void close() throws SQLException {
        connection.close();
    }
}
