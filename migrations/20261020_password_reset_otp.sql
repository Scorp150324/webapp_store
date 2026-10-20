USE store_management_db;

SET @customer_username_column_exists = (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'Customers'
    AND COLUMN_NAME = 'Username'
);
SET @customer_username_column_ddl = IF(
  @customer_username_column_exists = 0,
  'ALTER TABLE Customers ADD COLUMN Username VARCHAR(50) NULL UNIQUE AFTER FullName',
  'SELECT 1'
);
PREPARE customer_username_column_stmt FROM @customer_username_column_ddl;
EXECUTE customer_username_column_stmt;
DEALLOCATE PREPARE customer_username_column_stmt;

CREATE TABLE IF NOT EXISTS Password_Reset_Tokens (
  PasswordResetID BIGINT AUTO_INCREMENT PRIMARY KEY,
  UserID INT,
  CustomerID INT,
  TokenHash CHAR(64) NOT NULL UNIQUE COMMENT 'HMAC-SHA-256 hash of the OTP',
  ExpiresAt DATETIME NOT NULL,
  UsedAt DATETIME,
  FailedAttempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_password_reset_expiry (ExpiresAt, UsedAt),
  CONSTRAINT chk_password_reset_account CHECK (
    (UserID IS NOT NULL AND CustomerID IS NULL)
    OR (UserID IS NULL AND CustomerID IS NOT NULL)
  ),
  CONSTRAINT fk_password_reset_user FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
  CONSTRAINT fk_password_reset_customer FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @password_reset_attempt_column_exists = (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'Password_Reset_Tokens'
    AND COLUMN_NAME = 'FailedAttempts'
);
SET @password_reset_attempt_column_ddl = IF(
  @password_reset_attempt_column_exists = 0,
  'ALTER TABLE Password_Reset_Tokens ADD COLUMN FailedAttempts TINYINT UNSIGNED NOT NULL DEFAULT 0',
  'SELECT 1'
);
PREPARE password_reset_attempt_column_stmt
  FROM @password_reset_attempt_column_ddl;
EXECUTE password_reset_attempt_column_stmt;
DEALLOCATE PREPARE password_reset_attempt_column_stmt;
