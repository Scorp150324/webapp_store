-- ============================================================
-- STORE MANAGEMENT SYSTEM SCHEMA & SAMPLE DATA
-- Target Database: MySQL 8.0+
-- (Không bao gồm câu lệnh CREATE DATABASE / USE DATABASE)
-- ============================================================
CREATE DATABASE IF NOT EXISTS store_management_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE store_management_db;
-- ============================================================
-- STORE MANAGEMENT SYSTEM SCHEMA & SAMPLE DATA
-- Target Database: MySQL 8.0+
-- (Hình ảnh lấy trực tiếp từ link trang web / Unsplash / Wikimedia)
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

-- Drop existing tables if present
DROP TABLE IF EXISTS Warranties;
DROP TABLE IF EXISTS Payment_Transactions;
DROP TABLE IF EXISTS Payments;
DROP TABLE IF EXISTS Order_Details;
DROP TABLE IF EXISTS Orders;
DROP TABLE IF EXISTS Inbound_Details;
DROP TABLE IF EXISTS Inbound_Notes;
DROP TABLE IF EXISTS Product_Serials;
DROP TABLE IF EXISTS Product_Images;
DROP TABLE IF EXISTS Products;
DROP TABLE IF EXISTS Suppliers;
DROP TABLE IF EXISTS Categories;
DROP TABLE IF EXISTS Promotions;
DROP TABLE IF EXISTS Customer_Addresses;
DROP TABLE IF EXISTS Customers;
DROP TABLE IF EXISTS Customer_Groups;
DROP TABLE IF EXISTS User_Logs;
DROP TABLE IF EXISTS Role_Permissions;
DROP TABLE IF EXISTS Permissions;
DROP TABLE IF EXISTS Users;
DROP TABLE IF EXISTS Roles;

SET FOREIGN_KEY_CHECKS = 1;

-- ==========================================
-- 1. PHÂN HỆ PHÂN QUYỀN (RBAC) & TÀI KHOẢN
-- ==========================================

CREATE TABLE Roles (
  RoleID INT AUTO_INCREMENT PRIMARY KEY,
  RoleName VARCHAR(50) NOT NULL UNIQUE COMMENT 'ADMIN, SALES, WAREHOUSE, CASHIER',
  Description VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Permissions (
  PermissionID INT AUTO_INCREMENT PRIMARY KEY,
  PermissionCode VARCHAR(100) NOT NULL UNIQUE COMMENT 'PRODUCT_CREATE, ORDER_DELETE, REPORT_VIEW...',
  PermissionName VARCHAR(150) NOT NULL,
  Module VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Role_Permissions (
  RoleID INT NOT NULL,
  PermissionID INT NOT NULL,
  PRIMARY KEY (RoleID, PermissionID),
  CONSTRAINT fk_rp_role FOREIGN KEY (RoleID) REFERENCES Roles(RoleID) ON DELETE CASCADE,
  CONSTRAINT fk_rp_permission FOREIGN KEY (PermissionID) REFERENCES Permissions(PermissionID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Users (
  UserID INT AUTO_INCREMENT PRIMARY KEY,
  RoleID INT,
  Username VARCHAR(50) NOT NULL UNIQUE,
  PasswordHash VARCHAR(255) NOT NULL,
  FullName VARCHAR(100) NOT NULL,
  Email VARCHAR(100) UNIQUE,
  Phone VARCHAR(20),
  IsDeleted TINYINT DEFAULT 0 COMMENT '0: Đang hoạt động, 1: Đã xóa',
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  DeletedAt DATETIME COMMENT 'Ngày xóa mềm',
  CONSTRAINT fk_users_role FOREIGN KEY (RoleID) REFERENCES Roles(RoleID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE User_Logs (
  LogID BIGINT AUTO_INCREMENT PRIMARY KEY,
  UserID INT,
  Action VARCHAR(100) NOT NULL,
  Module VARCHAR(50) NOT NULL,
  IPAddress VARCHAR(45),
  UserAgent VARCHAR(255),
  Description TEXT,
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_logs_user FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================
-- 2. PHÂN HỆ KHÁCH HÀNG (CRM) & KHUYẾN MÃI
-- ==========================================

CREATE TABLE Customer_Groups (
  GroupID INT AUTO_INCREMENT PRIMARY KEY,
  GroupName VARCHAR(50) NOT NULL COMMENT 'Đồng, Bạc, Vàng, Kim Cương',
  DiscountPercent DECIMAL(5,2) DEFAULT 0.00,
  MinSpent DECIMAL(15,2) DEFAULT 0.00
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Customers (
  CustomerID INT AUTO_INCREMENT PRIMARY KEY,
  GroupID INT,
  FullName VARCHAR(100) NOT NULL,
  Phone VARCHAR(20) NOT NULL UNIQUE,
  Email VARCHAR(100),
  TotalSpent DECIMAL(15,2) DEFAULT 0.00,
  RewardPoints INT DEFAULT 0,
  IsDeleted TINYINT DEFAULT 0 COMMENT '0: Đang hoạt động, 1: Đã xóa',
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  DeletedAt DATETIME COMMENT 'Ngày xóa mềm',
  CONSTRAINT fk_customers_group FOREIGN KEY (GroupID) REFERENCES Customer_Groups(GroupID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Customer_Addresses (
  AddressID INT AUTO_INCREMENT PRIMARY KEY,
  CustomerID INT NOT NULL,
  ReceiverName VARCHAR(100) NOT NULL,
  ReceiverPhone VARCHAR(20) NOT NULL,
  AddressDetail VARCHAR(255) NOT NULL,
  ProvinceCity VARCHAR(100) NOT NULL,
  IsDefault BOOLEAN DEFAULT FALSE,
  CONSTRAINT fk_addresses_customer FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Promotions (
  PromotionID INT AUTO_INCREMENT PRIMARY KEY,
  Code VARCHAR(50) NOT NULL UNIQUE,
  Title VARCHAR(150) NOT NULL,
  DiscountType VARCHAR(20) NOT NULL COMMENT 'PERCENT, FIXED_AMOUNT',
  DiscountValue DECIMAL(15,2) NOT NULL,
  MinOrderAmount DECIMAL(15,2) DEFAULT 0.00,
  MaxDiscountAmount DECIMAL(15,2),
  UsageLimit INT DEFAULT 0 COMMENT '0 = Không giới hạn',
  UsedCount INT DEFAULT 0,
  StartDate DATETIME NOT NULL,
  EndDate DATETIME NOT NULL,
  IsActive BOOLEAN DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================
-- 3. PHÂN HỆ PRODUCT, SERIAL & QUẢN LÝ KHO
-- ==========================================

CREATE TABLE Categories (
  CategoryID INT AUTO_INCREMENT PRIMARY KEY,
  CategoryName VARCHAR(100) NOT NULL,
  ParentID INT COMMENT 'Danh mục cha-con',
  Description TEXT,
  CONSTRAINT fk_categories_parent FOREIGN KEY (ParentID) REFERENCES Categories(CategoryID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Suppliers (
  SupplierID INT AUTO_INCREMENT PRIMARY KEY,
  SupplierName VARCHAR(150) NOT NULL,
  Phone VARCHAR(20),
  Email VARCHAR(100),
  Address VARCHAR(255),
  TaxCode VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Products (
  ProductID INT AUTO_INCREMENT PRIMARY KEY,
  CategoryID INT,
  SupplierID INT,
  SKU VARCHAR(50) NOT NULL UNIQUE,
  Barcode VARCHAR(50) UNIQUE,
  ProductName VARCHAR(200) NOT NULL,
  MainImage VARCHAR(500) COMMENT 'URL ảnh đại diện chính',
  Specifications TEXT,
  CostPrice DECIMAL(15,2) NOT NULL DEFAULT 0.00,
  SellingPrice DECIMAL(15,2) NOT NULL,
  StockQuantity INT DEFAULT 0,
  WarrantyMonths INT DEFAULT 12,
  IsHasSerial BOOLEAN DEFAULT TRUE,
  IsDeleted TINYINT DEFAULT 0,
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  DeletedAt DATETIME,
  CONSTRAINT fk_products_category FOREIGN KEY (CategoryID) REFERENCES Categories(CategoryID) ON DELETE SET NULL,
  CONSTRAINT fk_products_supplier FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Product_Images (
  ImageID INT AUTO_INCREMENT PRIMARY KEY,
  ProductID INT NOT NULL,
  ImageUrl VARCHAR(500) NOT NULL,
  IsMain BOOLEAN DEFAULT FALSE,
  SortOrder INT DEFAULT 0,
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_images_product FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Product_Serials (
  SerialID INT AUTO_INCREMENT PRIMARY KEY,
  ProductID INT NOT NULL,
  SerialNumber VARCHAR(100) NOT NULL UNIQUE,
  Status VARCHAR(20) DEFAULT 'AVAILABLE' COMMENT 'AVAILABLE, SOLD, WARRANTY, DEFECTIVE',
  InboundDetailID INT COMMENT 'Nhập từ phiếu nào',
  OrderDetailID INT COMMENT 'Xuất ở đơn hàng nào',
  CONSTRAINT fk_serials_product FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Inbound_Notes (
  InboundID INT AUTO_INCREMENT PRIMARY KEY,
  SupplierID INT,
  CreatedBy INT,
  ImportDate DATETIME DEFAULT CURRENT_TIMESTAMP,
  TotalAmount DECIMAL(15,2) NOT NULL,
  Status VARCHAR(20) DEFAULT 'COMPLETED' COMMENT 'DRAFT, COMPLETED, CANCELLED',
  Notes TEXT,
  CONSTRAINT fk_inbound_supplier FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID) ON DELETE SET NULL,
  CONSTRAINT fk_inbound_user FOREIGN KEY (CreatedBy) REFERENCES Users(UserID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Inbound_Details (
  InboundDetailID INT AUTO_INCREMENT PRIMARY KEY,
  InboundID INT NOT NULL,
  ProductID INT NOT NULL,
  Quantity INT NOT NULL,
  ImportPrice DECIMAL(15,2) NOT NULL,
  CONSTRAINT fk_indetail_note FOREIGN KEY (InboundID) REFERENCES Inbound_Notes(InboundID) ON DELETE CASCADE,
  CONSTRAINT fk_indetail_product FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE Product_Serials
  ADD CONSTRAINT fk_serials_inbound FOREIGN KEY (InboundDetailID) REFERENCES Inbound_Details(InboundDetailID) ON DELETE SET NULL;

-- ==========================================
-- 4. PHÂN HỆ ĐƠN HÀNG, THANH TOÁN & BẢO HÀNH
-- ==========================================

CREATE TABLE Orders (
  OrderID INT AUTO_INCREMENT PRIMARY KEY,
  OrderCode VARCHAR(50) NOT NULL UNIQUE COMMENT 'Mã đơn dạng HD20261009-001',
  CustomerID INT,
  EmployeeID INT,
  PromotionID INT,
  SubTotal DECIMAL(15,2) NOT NULL COMMENT 'Tiền hàng chưa giảm',
  DiscountAmount DECIMAL(15,2) DEFAULT 0.00 COMMENT 'Số tiền được giảm',
  TotalAmount DECIMAL(15,2) NOT NULL COMMENT 'Tổng tiền phải thanh toán',
  OrderStatus VARCHAR(20) DEFAULT 'PENDING' COMMENT 'PENDING, PAID, SHIPPED, COMPLETED, CANCELLED',
  OrderDate DATETIME DEFAULT CURRENT_TIMESTAMP,
  Notes TEXT,
  CONSTRAINT fk_orders_customer FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE SET NULL,
  CONSTRAINT fk_orders_employee FOREIGN KEY (EmployeeID) REFERENCES Users(UserID) ON DELETE SET NULL,
  CONSTRAINT fk_orders_promotion FOREIGN KEY (PromotionID) REFERENCES Promotions(PromotionID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Order_Details (
  OrderDetailID INT AUTO_INCREMENT PRIMARY KEY,
  OrderID INT NOT NULL,
  ProductID INT NOT NULL,
  Quantity INT NOT NULL,
  UnitPrice DECIMAL(15,2) NOT NULL,
  TotalPrice DECIMAL(15,2) NOT NULL,
  CONSTRAINT fk_odetail_order FOREIGN KEY (OrderID) REFERENCES Orders(OrderID) ON DELETE CASCADE,
  CONSTRAINT fk_odetail_product FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE Product_Serials
  ADD CONSTRAINT fk_serials_orderdetail FOREIGN KEY (OrderDetailID) REFERENCES Order_Details(OrderDetailID) ON DELETE SET NULL;

CREATE TABLE Payments (
  PaymentID INT AUTO_INCREMENT PRIMARY KEY,
  OrderID INT NOT NULL,
  Amount DECIMAL(15,2) NOT NULL,
  PaidAmount DECIMAL(15,2) DEFAULT 0.00,
  PaymentMethod VARCHAR(20) NOT NULL COMMENT 'CASH, BANK_TRANSFER, CARD, MOMO, VNPAY',
  PaymentStatus VARCHAR(20) DEFAULT 'UNPAID' COMMENT 'UNPAID, PARTIALLY_PAID, PAID, REFUNDED',
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_payments_order FOREIGN KEY (OrderID) REFERENCES Orders(OrderID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Payment_Transactions (
  TransactionID INT AUTO_INCREMENT PRIMARY KEY,
  PaymentID INT NOT NULL,
  TransCode VARCHAR(100),
  Amount DECIMAL(15,2) NOT NULL,
  PayGateway VARCHAR(50),
  GatewayResponse TEXT,
  Status VARCHAR(20) DEFAULT 'PENDING' COMMENT 'PENDING, SUCCESS, FAILED',
  TransactionTime DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ptrans_payment FOREIGN KEY (PaymentID) REFERENCES Payments(PaymentID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Warranties (
  WarrantyID INT AUTO_INCREMENT PRIMARY KEY,
  OrderDetailID INT NOT NULL,
  SerialNumber VARCHAR(100) NOT NULL,
  StartDate DATE NOT NULL,
  EndDate DATE NOT NULL,
  Status VARCHAR(20) DEFAULT 'ACTIVE' COMMENT 'ACTIVE, EXPIRED, CLAIMED',
  CONSTRAINT fk_warranties_odetail FOREIGN KEY (OrderDetailID) REFERENCES Order_Details(OrderDetailID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- DỮ LIỆU MẪU ĐẦY ĐỦ VỚI LINK HÌNH ẢNH TRỰC TUYẾN
-- ============================================================

-- 1. Roles (5 records)
INSERT INTO Roles (RoleID, RoleName, Description) VALUES
(1, 'ADMIN', 'Quản trị viên toàn hệ thống'),
(2, 'SALES', 'Nhân viên bán hàng'),
(3, 'WAREHOUSE', 'Nhân viên quản lý kho'),
(4, 'CASHIER', 'Nhân viên thu ngân'),
(5, 'MANAGER', 'Quản lý cửa hàng');

-- 2. Permissions (12 records)
INSERT INTO Permissions (PermissionID, PermissionCode, PermissionName, Module) VALUES
(1, 'USER_VIEW', 'Xem danh sách người dùng', 'USER'),
(2, 'USER_MANAGE', 'Thêm/Sửa/Xóa người dùng', 'USER'),
(3, 'PRODUCT_VIEW', 'Xem danh sách sản phẩm', 'PRODUCT'),
(4, 'PRODUCT_CREATE', 'Thêm sản phẩm mới', 'PRODUCT'),
(5, 'PRODUCT_EDIT', 'Chỉnh sửa sản phẩm', 'PRODUCT'),
(6, 'INBOUND_CREATE', 'Tạo phiếu nhập kho', 'WAREHOUSE'),
(7, 'ORDER_CREATE', 'Tạo đơn hàng mới', 'ORDER'),
(8, 'ORDER_CANCEL', 'Hủy đơn hàng', 'ORDER'),
(9, 'PAYMENT_PROCESS', 'Xử lý thanh toán', 'PAYMENT'),
(10, 'REPORT_VIEW', 'Xem báo cáo doanh thu', 'REPORT'),
(11, 'CUSTOMER_MANAGE', 'Quản lý thông tin khách hàng', 'CRM'),
(12, 'PROMOTION_MANAGE', 'Quản lý chương trình khuyến mãi', 'PROMOTION');

-- 3. Role_Permissions (29 records)
INSERT INTO Role_Permissions (RoleID, PermissionID) VALUES
(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (1, 12),
(2, 3), (2, 7), (2, 11),
(3, 3), (3, 4), (3, 5), (3, 6),
(4, 3), (4, 7), (4, 9),
(5, 3), (5, 7), (5, 8), (5, 9), (5, 10), (5, 11), (5, 12);

-- 4. Users (10 records)
INSERT INTO Users (UserID, RoleID, Username, PasswordHash, FullName, Email, Phone) VALUES
(1, 1, 'admin_super', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Nguyễn Văn Quản Trị', 'admin@store.com', '0901000001'),
(2, 5, 'manager_hung', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Trần Văn Hùng', 'hung.tv@store.com', '0901000002'),
(3, 2, 'sales_linh', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Lê Thị Mỹ Linh', 'linh.ltm@store.com', '0901000003'),
(4, 2, 'sales_tuan', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Phạm Anh Tuấn', 'tuan.pa@store.com', '0901000004'),
(5, 3, 'kho_dung', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Hoàng Tấn Dũng', 'dung.ht@store.com', '0901000005'),
(6, 3, 'kho_hoa', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Vũ Thị Hoa', 'hoa.vt@store.com', '0901000006'),
(7, 4, 'cashier_trang', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Đặng Thu Trang', 'trang.dt@store.com', '0901000007'),
(8, 4, 'cashier_minh', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Ngô Quang Minh', 'minh.nq@store.com', '0901000008'),
(9, 2, 'sales_mai', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Nguyễn Tuyết Mai', 'mai.nt@store.com', '0901000009'),
(10, 3, 'kho_nam', '$2a$12$eImiTXuWVxfM37uY4JANjOQx5T6/X/zO1qD8H6W71N0Zg0K6y2k8i', 'Bùi Hải Nam', 'nam.bh@store.com', '0901000010');

-- 5. User_Logs (10 records)
INSERT INTO User_Logs (LogID, UserID, Action, Module, IPAddress, UserAgent, Description, CreatedAt) VALUES
(1, 1, 'LOGIN', 'AUTH', '192.168.1.10', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Đăng nhập hệ thống thành công', '2026-10-01 08:00:00'),
(2, 5, 'CREATE_INBOUND', 'WAREHOUSE', '192.168.1.15', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Tạo phiếu nhập PN20261001-01', '2026-10-01 09:30:00'),
(3, 3, 'CREATE_ORDER', 'ORDER', '192.168.1.20', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Tạo đơn hàng HD20261001-001', '2026-10-01 10:15:00'),
(4, 7, 'PAYMENT', 'PAYMENT', '192.168.1.25', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Thanh toán đơn hàng HD20261001-001', '2026-10-01 10:20:00'),
(5, 1, 'CREATE_USER', 'USER', '192.168.1.10', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Thêm người dùng sales_mai', '2026-10-02 08:45:00'),
(6, 4, 'CREATE_ORDER', 'ORDER', '192.168.1.21', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Tạo đơn hàng HD20261002-002', '2026-10-02 11:10:00'),
(7, 8, 'PAYMENT', 'PAYMENT', '192.168.1.26', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Thanh toán đơn hàng HD20261002-002', '2026-10-02 11:15:00'),
(8, 2, 'CREATE_PROMOTION', 'PROMOTION', '192.168.1.11', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Tạo mã KM KHATVANG2026', '2026-10-03 14:00:00'),
(9, 6, 'UPDATE_STOCK', 'WAREHOUSE', '192.168.1.16', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Cập nhật số lượng kho Máy in Canon', '2026-10-04 16:30:00'),
(10, 3, 'CREATE_ORDER', 'ORDER', '192.168.1.20', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Tạo đơn hàng HD20261005-003', '2026-10-05 09:00:00');

-- 6. Customer_Groups (4 records)
INSERT INTO Customer_Groups (GroupID, GroupName, DiscountPercent, MinSpent) VALUES
(1, 'Đồng', 0.00, 0.00),
(2, 'Bạc', 2.00, 10000000.00),
(3, 'Vàng', 5.00, 30000000.00),
(4, 'Kim Cương', 10.00, 100000000.00);

-- 7. Customers (10 records)
INSERT INTO Customers (CustomerID, GroupID, FullName, Phone, Email, TotalSpent, RewardPoints) VALUES
(1, 4, 'Phạm Quốc Bảo', '0988111222', 'bao.pq@gmail.com', 125000000.00, 1250),
(2, 3, 'Trần Thu Hà', '0988222333', 'ha.tt@gmail.com', 42000000.00, 420),
(3, 2, 'Nguyễn Tiến Dũng', '0988333444', 'dung.nt@gmail.com', 18500000.00, 185),
(4, 1, 'Đỗ Thị Huệ', '0988444555', 'hue.dt@gmail.com', 5200000.00, 52),
(5, 3, 'Lê Hoàng Nam', '0988555666', 'nam.lh@gmail.com', 35000000.00, 350),
(6, 2, 'Ngô Thanh Vân', '0988666777', 'van.nt@gmail.com', 12000000.00, 120),
(7, 1, 'Hoàng Minh Trí', '0988777888', 'tri.hm@gmail.com', 3200000.00, 32),
(8, 4, 'Vũ Đình Phong', '0988888999', 'phong.vd@gmail.com', 110000000.00, 1100),
(9, 1, 'Bùi Phương Thảo', '0988999000', 'thao.bp@gmail.com', 0.00, 0),
(10, 2, 'Đinh Văn Khoa', '0988000111', 'khoa.dv@gmail.com', 15000000.00, 150);

-- 8. Customer_Addresses (10 records)
INSERT INTO Customer_Addresses (AddressID, CustomerID, ReceiverName, ReceiverPhone, AddressDetail, ProvinceCity, IsDefault) VALUES
(1, 1, 'Phạm Quốc Bảo', '0988111222', '123 Nguyễn Huệ, Phường Bến Nghé, Quận 1', 'TP. Hồ Chí Minh', 1),
(2, 2, 'Trần Thu Hà', '0988222333', '45 Hoàng Hoa Thám, Phường 6, Quận Bình Thạnh', 'TP. Hồ Chí Minh', 1),
(3, 3, 'Nguyễn Tiến Dũng', '0988333444', '88 Cầu Giấy, Phường Láng Thượng, Quận Cầu Giấy', 'Hà Nội', 1),
(4, 4, 'Đỗ Thị Huệ', '0988444555', '12 Lý Thường Kiệt, Phường 1', 'TP. Mỹ Tho, Tiền Giang', 1),
(5, 5, 'Lê Hoàng Nam', '0988555666', '56 Nguyễn Văn Linh, Phường Nam Dương, Quận Hải Châu', 'Đà Nẵng', 1),
(6, 6, 'Ngô Thanh Vân', '0988666777', '230 Lê Hồng Phong, Phường 4, Quận 5', 'TP. Hồ Chí Minh', 1),
(7, 7, 'Hoàng Minh Trí', '0988777888', '15 Trần Phú, Phường Điện Biên, Quận Ba Đình', 'Hà Nội', 1),
(8, 8, 'Vũ Đình Phong', '0988888999', '99 Nguyễn Trãi, Phường Bến Thành, Quận 1', 'TP. Hồ Chí Minh', 1),
(9, 9, 'Bùi Phương Thảo', '0988999000', '74 Đường 3/2, Phường Xuân Khánh, Quận Ninh Kiều', 'Cần Thơ', 1),
(10, 10, 'Đinh Văn Khoa', '0988000111', '321 Hùng Vương, Phường 2', 'TP. Tân An, Long An', 1);

-- 9. Promotions (10 records)
INSERT INTO Promotions (PromotionID, Code, Title, DiscountType, DiscountValue, MinOrderAmount, MaxDiscountAmount, UsageLimit, UsedCount, StartDate, EndDate, IsActive) VALUES
(1, 'KMKM10', 'Giảm 10% đơn hàng khai trương', 'PERCENT', 10.00, 1000000.00, 500000.00, 100, 15, '2026-01-01 00:00:00', '2026-12-31 23:59:59', 1),
(2, 'GIAM50K', 'Giảm 50k cho đơn từ 2 triệu', 'FIXED_AMOUNT', 50000.00, 2000000.00, 50000.00, 200, 45, '2026-05-01 00:00:00', '2026-12-31 23:59:59', 1),
(3, 'LAPTOPVIP', 'Giảm 1 triệu cho Laptop trên 20tr', 'FIXED_AMOUNT', 1000000.00, 20000000.00, 1000000.00, 50, 8, '2026-09-01 00:00:00', '2026-11-30 23:59:59', 1),
(4, 'OCTOBER5', 'Giảm 5% chào tháng 10', 'PERCENT', 5.00, 5000000.00, 1000000.00, 100, 12, '2026-10-01 00:00:00', '2026-10-31 23:59:59', 1),
(5, 'BLACKFRIDAY', 'Săn deal khủng Black Friday', 'PERCENT', 20.00, 3000000.00, 2000000.00, 500, 0, '2026-11-20 00:00:00', '2026-11-30 23:59:59', 1),
(6, 'TRIANVIP', 'Ưu đãi Khách hàng Vàng & Kim Cương', 'PERCENT', 8.00, 10000000.00, 1500000.00, 50, 5, '2026-01-01 00:00:00', '2026-12-31 23:59:59', 1),
(7, 'PHUKIEN100', 'Giảm 100k khi mua phụ kiện', 'FIXED_AMOUNT', 100000.00, 500000.00, 100000.00, 300, 80, '2026-01-01 00:00:00', '2026-12-31 23:59:59', 1),
(8, 'BACKTOSCHOOL', 'Chương trình Tựu trường', 'PERCENT', 7.00, 2000000.00, 700000.00, 150, 150, '2026-08-01 00:00:00', '2026-09-30 23:59:59', 0),
(9, 'MAMOI200', 'Voucher người dùng mới', 'FIXED_AMOUNT', 200000.00, 3000000.00, 200000.00, 100, 22, '2026-01-01 00:00:00', '2026-12-31 23:59:59', 1),
(10, 'TET2026', 'Đón Tết Rực Rỡ', 'PERCENT', 15.00, 5000000.00, 3000000.00, 200, 0, '2026-12-15 00:00:00', '2027-02-15 23:59:59', 1);

-- 10. Categories (10 records)
INSERT INTO Categories (CategoryID, CategoryName, ParentID, Description) VALUES
(1, 'Laptop', NULL, 'Máy tính xách tay các thương hiệu'),
(2, 'Máy Tính Để Bàn (PC)', NULL, 'Máy tính đồng bộ và PC Gaming tự ráp'),
(3, 'Máy In & Thiết Bị Văn Phòng', NULL, 'Máy in laser, máy in phun, máy quét Scanner'),
(4, 'Camera & Thiết Bị An Ninh', NULL, 'Camera IP Wifi, Webcam, Camera giám sát'),
(5, 'Điện Thoại Thông Minh', NULL, 'Smartphone Apple, Samsung, Xiaomi...'),
(6, 'Linh Kiện Máy Tính', NULL, 'RAM, CPU, VGA, Ổ cứng SSD/HDD, Mainboard'),
(7, 'Phụ Kiện & Thiết Bị Ngoại Vi', NULL, 'Bàn phím, chuột, tai nghe, cáp sạc'),
(8, 'Máy In Laser', 3, 'Máy in laser đơn năng và đa năng'),
(9, 'Camera Giám Sát IP', 4, 'Camera an ninh trong nhà và ngoài trời'),
(10, 'PC Gaming', 2, 'Máy tính chơi game cấu hình cao');

-- 11. Suppliers (10 records)
INSERT INTO Suppliers (SupplierID, SupplierName, Phone, Email, Address, TaxCode) VALUES
(1, 'Công ty TNHH Apple Việt Nam', '02838221122', 'contact@apple.com.vn', 'Tầng 15, Bitexco Financial Tower, Q1, TP.HCM', '0301234567'),
(2, 'Công ty TNHH Canon Marketing Việt Nam', '02838200000', 'info@canon.com.vn', 'Tầng 25, Vincom Center, Q1, TP.HCM', '0302233445'),
(3, 'Công ty Cổ phần Hikvision Việt Nam', '02439998888', 'sales@hikvision.vn', 'Số 88 Thanh Nhàn, Q.Hai Bà Trưng, Hà Nội', '0103344556'),
(4, 'Công ty TNHH Dell Global B.V Việt Nam', '02838234567', 'sales@dell.com.vn', 'Tầng 26, Landmark 81, Q.Bình Thạnh, TP.HCM', '0303456789'),
(5, 'Công ty TNHH Asus Việt Nam', '02839308888', 'support@asus.com.vn', 'Tầng 8, Tòa nhà Viettel, Q10, TP.HCM', '0302345678'),
(6, 'Công ty Cổ phần Logitech Việt Nam', '02839100011', 'logi@logitech.com.vn', 'Số 12 Nam Kỳ Khởi Nghĩa, Q1, TP.HCM', '0305678901'),
(7, 'Công ty TNHH Samsung Electronics Việt Nam', '02437711111', 'info@samsung.com.vn', 'KCN Yên Phong, Bắc Ninh', '2300123456'),
(8, 'Công ty TNHH HP Việt Nam', '02839112266', 'hp.vietnam@hp.com', 'Tầng 10, Saigon Tower, Q1, TP.HCM', '0306677889'),
(9, 'Công ty TNHH Ezviz Việt Nam', '02838119900', 'support@ezviz.vn', '120 Nguyễn Văn Trỗi, Q.Phú Nhuận, TP.HCM', '0308899001'),
(10, 'Công ty TNHH MSI Việt Nam', '02838112233', 'vn@msi.com', 'Tầng 5, Tòa nhà Hải Âu, Q.Tân Bình, TP.HCM', '0304567890');

-- 12. Products (10 records - Cập nhật link ảnh thực tế từ internet)
INSERT INTO Products (ProductID, CategoryID, SupplierID, SKU, Barcode, ProductName, MainImage, Specifications, CostPrice, SellingPrice, StockQuantity, WarrantyMonths, IsHasSerial) VALUES
(1, 8, 2, 'CANON-LBP2900', '496099927123', 'Máy in Laser Canon LBP 2900 (Đơn năng, Khổ A4)', 'https://images.unsplash.com/photo-1612815154858-60aa4c59eaa6?auto=format&fit=crop&w=800&q=80', 'Tốc độ: 12 trang/phút, Khổ giấy: A4, Độ phân giải: 2400 x 600 dpi, Cổng kết nối: USB 2.0', 3800000.00, 4450000.00, 30, 12, 1),
(2, 9, 9, 'EZVIZ-C6N-1080P', '694154581234', 'Camera Wifi Ezviz C6N 1080P 2MP Xoay 360 độ', 'https://images.unsplash.com/photo-1557597774-9d273605dfa9?auto=format&fit=crop&w=800&q=80', 'Độ phân giải: Full HD 1080p, Góc xoay: 360 độ, Hồng ngoại đêm: 10m, Đàm thoại 2 chiều', 450000.00, 690000.00, 50, 24, 1),
(3, 10, 5, 'PC-ASUS-ROG-STRIX', '471108199001', 'PC Gaming ASUS ROG Strix i7-13700F / RTX 4070 / 32GB RAM / 1TB SSD', 'https://images.unsplash.com/photo-1587202372775-e229f172b9d7?auto=format&fit=crop&w=800&q=80', 'CPU: i7-13700F, RAM: 32GB DDR5, SSD: 1TB NVMe, VGA: RTX 4070 12GB, Nguồn: 750W 80 Plus Gold', 35000000.00, 41990000.00, 8, 36, 1),
(4, 1, 4, 'DELL-XPS13-9315', '884116380123', 'Laptop Dell XPS 13 9315 i7-1250U / 16GB / 512GB SSD', 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=800&q=80', 'CPU: i7-1250U, RAM: 16GB LPDDR5, SSD: 512GB NVMe, Màn: 13.4 inch FHD+', 25000000.00, 29990000.00, 15, 12, 1),
(5, 5, 1, 'IPHONE-15PM-256', '195949012345', 'iPhone 15 Pro Max 256GB Titanium Tự Nhiên', 'https://images.unsplash.com/photo-1695048133142-1a20484d2569?auto=format&fit=crop&w=800&q=80', 'Màn: 6.7 inch Super Retina XDR, Chip: A17 Pro, Cam: 48MP + 12MP + 12MP', 28500000.00, 32990000.00, 25, 12, 1),
(6, 3, 8, 'HP-NEVERSTOP-1000W', '193808112233', 'Máy in Laser HP Neverstop 1000w In Wifi', 'https://images.unsplash.com/photo-1563206767-5b18f218e8de?auto=format&fit=crop&w=800&q=80', 'Tốc độ: 20 trang/phút, Khổ giấy: A4, Kết nối: USB / Wifi, Hộp mực nạp lại cực nhanh', 3200000.00, 3890000.00, 20, 12, 1),
(7, 4, 3, 'HIKVISION-DS2CD2143', '695427361234', 'Camera IP Dome Hikvision DS-2CD2143G0-I 4MP Chuẩn Báo Động', 'https://images.unsplash.com/photo-1528312457262-f67f2e153093?auto=format&fit=crop&w=800&q=80', 'Độ phân giải: 4 Megapixel, Chuẩn nén H.265+, Chống nước IP67, Vỏ kim loại chống đập', 1200000.00, 1650000.00, 40, 24, 1),
(8, 2, 4, 'PC-DELL-INSPIRON-3020', '884116441111', 'Máy tính để bàn PC Dell Inspiron 3020 MT i5-13400 / 8GB / 512GB', 'https://images.unsplash.com/photo-1547082299-de196ea013d6?auto=format&fit=crop&w=800&q=80', 'CPU: i5-13400, RAM: 8GB DDR4, SSD: 512GB, Đi kèm Bàn phím + Chuột Dell', 11500000.00, 13990000.00, 12, 12, 1),
(9, 7, 6, 'LOGI-BRIO-4K', '097855998877', 'Webcam 4K Logitech Brio Ultra HD Tích Hợp Mic Đôi', 'https://images.unsplash.com/photo-1587826080692-f439cd0b70da?auto=format&fit=crop&w=800&q=80', 'Độ phân giải: 4K Ultra HD, Cảm biến IR nhận diện khuôn mặt Windows Hello, Mic giảm tiếng ồn', 3600000.00, 4490000.00, 25, 24, 1),
(10, 5, 7, 'SS-S24ULTRA-512', '880609512345', 'Samsung Galaxy S24 Ultra 12GB/512GB Titanium Grey', 'https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?auto=format&fit=crop&w=800&q=80', 'Màn: 6.8 inch Dynamic AMOLED 2X, Chip: Snapdragon 8 Gen 3, Cam: 200MP', 26000000.00, 30990000.00, 20, 12, 1);

-- 13. Product_Images (10 records)
INSERT INTO Product_Images (ImageID, ProductID, ImageUrl, IsMain, SortOrder) VALUES
(1, 1, 'https://images.unsplash.com/photo-1612815154858-60aa4c59eaa6?auto=format&fit=crop&w=800&q=80', 1, 1),
(2, 2, 'https://images.unsplash.com/photo-1557597774-9d273605dfa9?auto=format&fit=crop&w=800&q=80', 1, 1),
(3, 3, 'https://images.unsplash.com/photo-1587202372775-e229f172b9d7?auto=format&fit=crop&w=800&q=80', 1, 1),
(4, 4, 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=800&q=80', 1, 1),
(5, 5, 'https://images.unsplash.com/photo-1695048133142-1a20484d2569?auto=format&fit=crop&w=800&q=80', 1, 1),
(6, 6, 'https://images.unsplash.com/photo-1563206767-5b18f218e8de?auto=format&fit=crop&w=800&q=80', 1, 1),
(7, 7, 'https://images.unsplash.com/photo-1528312457262-f67f2e153093?auto=format&fit=crop&w=800&q=80', 1, 1),
(8, 8, 'https://images.unsplash.com/photo-1547082299-de196ea013d6?auto=format&fit=crop&w=800&q=80', 1, 1),
(9, 9, 'https://images.unsplash.com/photo-1587826080692-f439cd0b70da?auto=format&fit=crop&w=800&q=80', 1, 1),
(10, 10, 'https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?auto=format&fit=crop&w=800&q=80', 1, 1);

-- 14. Inbound_Notes (10 records)
INSERT INTO Inbound_Notes (InboundID, SupplierID, CreatedBy, ImportDate, TotalAmount, Status, Notes) VALUES
(1, 2, 5, '2026-09-01 10:00:00', 114000000.00, 'COMPLETED', 'Nhập 30 Máy in Canon LBP 2900'),
(2, 9, 5, '2026-09-02 11:30:00', 22500000.00, 'COMPLETED', 'Nhập 50 Camera Ezviz C6N'),
(3, 5, 6, '2026-09-05 09:15:00', 280000000.00, 'COMPLETED', 'Nhập 8 PC Gaming Asus ROG Strix'),
(4, 4, 6, '2026-09-10 14:00:00', 375000000.00, 'COMPLETED', 'Nhập 15 Laptop Dell XPS 13'),
(5, 1, 5, '2026-09-12 15:45:00', 712500000.00, 'COMPLETED', 'Nhập 25 iPhone 15 Pro Max'),
(6, 8, 10, '2026-09-15 08:30:00', 64000000.00, 'COMPLETED', 'Nhập 20 Máy in Laser HP Neverstop'),
(7, 3, 5, '2026-09-18 10:20:00', 48000000.00, 'COMPLETED', 'Nhập 40 Camera Hikvision DS-2CD2143'),
(8, 4, 6, '2026-09-20 13:10:00', 138000000.00, 'COMPLETED', 'Nhập 12 PC Dell Inspiron 3020'),
(9, 6, 10, '2026-09-22 16:00:00', 90000000.00, 'COMPLETED', 'Nhập 25 Webcam 4K Logitech Brio'),
(10, 7, 5, '2026-09-25 09:50:00', 520000000.00, 'COMPLETED', 'Nhập 20 Samsung S24 Ultra');

-- 15. Inbound_Details (10 records)
INSERT INTO Inbound_Details (InboundDetailID, InboundID, ProductID, Quantity, ImportPrice) VALUES
(1, 1, 1, 30, 3800000.00),
(2, 2, 2, 50, 450000.00),
(3, 3, 3, 8, 35000000.00),
(4, 4, 4, 15, 25000000.00),
(5, 5, 5, 25, 28500000.00),
(6, 6, 6, 20, 3200000.00),
(7, 7, 7, 40, 1200000.00),
(8, 8, 8, 12, 11500000.00),
(9, 9, 9, 25, 3600000.00),
(10, 10, 10, 20, 26000000.00);

-- 16. Orders (10 records)
INSERT INTO Orders (OrderID, OrderCode, CustomerID, EmployeeID, PromotionID, SubTotal, DiscountAmount, TotalAmount, OrderStatus, OrderDate, Notes) VALUES
(1, 'HD20261001-001', 1, 3, 2, 4450000.00, 50000.00, 4400000.00, 'COMPLETED', '2026-10-01 10:15:00', 'Mua Máy in Canon LBP2900 cho văn phòng'),
(2, 'HD20261002-002', 2, 4, 7, 1380000.00, 100000.00, 1280000.00, 'COMPLETED', '2026-10-02 11:10:00', 'Lắp 2 Camera Ezviz C6N'),
(3, 'HD20261003-003', 3, 3, 3, 41990000.00, 1000000.00, 40990000.00, 'COMPLETED', '2026-10-03 14:30:00', 'Giao dàn PC Gaming ASUS ROG Strix'),
(4, 'HD20261004-004', 4, 9, 1, 29990000.00, 500000.00, 29490000.00, 'COMPLETED', '2026-10-04 09:20:00', 'Mua Laptop Dell XPS 13'),
(5, 'HD20261005-005', 5, 4, 6, 32990000.00, 1500000.00, 31490000.00, 'COMPLETED', '2026-10-05 16:45:00', 'Giao iPhone 15 Pro Max tại Đà Nẵng'),
(6, 'HD20261006-006', 6, 3, NULL, 3890000.00, 0.00, 3890000.00, 'SHIPPED', '2026-10-06 10:00:00', 'Đang vận chuyển Máy in HP Neverstop'),
(7, 'HD20261007-007', 7, 9, 2, 3300000.00, 50000.00, 3250000.00, 'COMPLETED', '2026-10-07 11:15:00', 'Mua 2 Camera Hikvision'),
(8, 'HD20261008-008', 8, 4, 4, 13990000.00, 699500.00, 13290500.00, 'PAID', '2026-10-08 13:20:00', 'Bộ PC Dell Inspiron văn phòng'),
(9, 'HD20261009-009', 10, 3, NULL, 4490000.00, 0.00, 4490000.00, 'PENDING', '2026-10-09 08:30:00', 'Chờ chuyển khoản mua Webcam Logitech 4K'),
(10, 'HD20261009-010', 1, 9, 1, 30990000.00, 500000.00, 30490000.00, 'COMPLETED', '2026-10-09 14:00:00', 'Khách VIP mua Samsung S24 Ultra');

-- 17. Order_Details (10 records)
INSERT INTO Order_Details (OrderDetailID, OrderID, ProductID, Quantity, UnitPrice, TotalPrice) VALUES
(1, 1, 1, 1, 4450000.00, 4450000.00),
(2, 2, 2, 2, 690000.00, 1380000.00),
(3, 3, 3, 1, 41990000.00, 41990000.00),
(4, 4, 4, 1, 29990000.00, 29990000.00),
(5, 5, 5, 1, 32990000.00, 32990000.00),
(6, 6, 6, 1, 3890000.00, 3890000.00),
(7, 7, 7, 2, 1650000.00, 3300000.00),
(8, 8, 8, 1, 13990000.00, 13990000.00),
(9, 9, 9, 1, 4490000.00, 4490000.00),
(10, 10, 10, 1, 30990000.00, 30990000.00);

-- 18. Product_Serials (12 records)
INSERT INTO Product_Serials (SerialID, ProductID, SerialNumber, Status, InboundDetailID, OrderDetailID) VALUES
(1, 1, 'CANON-2900-SN8801', 'SOLD', 1, 1),
(2, 1, 'CANON-2900-SN8802', 'AVAILABLE', 1, NULL),
(3, 2, 'EZVIZ-C6N-99101', 'SOLD', 2, 2),
(4, 2, 'EZVIZ-C6N-99102', 'SOLD', 2, 2),
(5, 3, 'ROG-STRIX-PC001', 'SOLD', 3, 3),
(6, 4, 'DELL-XPS-11001', 'SOLD', 4, 4),
(7, 5, 'IP15PM-88291001', 'SOLD', 5, 5),
(8, 6, 'HP-NS1000-77101', 'SOLD', 6, 6),
(9, 7, 'HIK-4MP-33201', 'SOLD', 7, 7),
(10, 8, 'DELL-PC3020-5511', 'SOLD', 8, 8),
(11, 9, 'LOGI-BRIO-4K-01', 'SOLD', 9, 9),
(12, 10, 'S24U-7761001', 'SOLD', 10, 10);

-- 19. Payments (10 records)
INSERT INTO Payments (PaymentID, OrderID, Amount, PaidAmount, PaymentMethod, PaymentStatus, CreatedAt) VALUES
(1, 1, 4400000.00, 4400000.00, 'CASH', 'PAID', '2026-10-01 10:20:00'),
(2, 2, 1280000.00, 1280000.00, 'MOMO', 'PAID', '2026-10-02 11:15:00'),
(3, 3, 40990000.00, 40990000.00, 'BANK_TRANSFER', 'PAID', '2026-10-03 14:35:00'),
(4, 4, 29490000.00, 29490000.00, 'CARD', 'PAID', '2026-10-04 09:22:00'),
(5, 5, 31490000.00, 31490000.00, 'VNPAY', 'PAID', '2026-10-05 16:50:00'),
(6, 6, 3890000.00, 3890000.00, 'BANK_TRANSFER', 'PAID', '2026-10-06 10:05:00'),
(7, 7, 3250000.00, 3250000.00, 'CASH', 'PAID', '2026-10-07 11:20:00'),
(8, 8, 13290500.00, 13290500.00, 'BANK_TRANSFER', 'PAID', '2026-10-08 13:25:00'),
(9, 9, 4490000.00, 0.00, 'BANK_TRANSFER', 'UNPAID', '2026-10-09 08:30:00'),
(10, 10, 30490000.00, 30490000.00, 'BANK_TRANSFER', 'PAID', '2026-10-09 14:05:00');

-- 20. Payment_Transactions (10 records)
INSERT INTO Payment_Transactions (TransactionID, PaymentID, TransCode, Amount, PayGateway, GatewayResponse, Status, TransactionTime) VALUES
(1, 1, 'CASH20261001001', 4400000.00, 'CASH_REGISTER', '{"status":"SUCCESS"}', 'SUCCESS', '2026-10-01 10:20:15'),
(2, 2, 'MM2026100299881', 1280000.00, 'MOMO', '{"resultCode":0,"message":"Successful"}', 'SUCCESS', '2026-10-02 11:15:30'),
(3, 3, 'VCB2026100311223', 40990000.00, 'VIETCOMBANK', '{"code":"00","message":"Success"}', 'SUCCESS', '2026-10-03 14:35:10'),
(4, 4, 'POS2026100444332', 29490000.00, 'BIDV_POS', '{"code":"00","message":"Approved"}', 'SUCCESS', '2026-10-04 09:22:05'),
(5, 5, 'VNP2026100588771', 31490000.00, 'VNPAY', '{"vnp_ResponseCode":"00"}', 'SUCCESS', '2026-10-05 16:50:45'),
(6, 6, 'TCB2026100655432', 3890000.00, 'TECHCOMBANK', '{"code":"00","message":"Success"}', 'SUCCESS', '2026-10-06 10:05:20'),
(7, 7, 'CASH20261007002', 3250000.00, 'CASH_REGISTER', '{"status":"SUCCESS"}', 'SUCCESS', '2026-10-07 11:20:00'),
(8, 8, 'ACB2026100877811', 13290500.00, 'ACB', '{"code":"00","message":"Success"}', 'SUCCESS', '2026-10-08 13:25:35'),
(9, 9, 'PEND20261009001', 4490000.00, 'VIETCOMBANK', '{"code":"09","message":"Pending payment"}', 'PENDING', '2026-10-09 08:30:00'),
(10, 10, 'VCB2026100999123', 30490000.00, 'VIETCOMBANK', '{"code":"00","message":"Success"}', 'SUCCESS', '2026-10-09 14:05:50');

-- 21. Warranties (10 records)
INSERT INTO Warranties (WarrantyID, OrderDetailID, SerialNumber, StartDate, EndDate, Status) VALUES
(1, 1, 'CANON-2900-SN8801', '2026-10-01', '2027-10-01', 'ACTIVE'),
(2, 2, 'EZVIZ-C6N-99101', '2026-10-02', '2028-10-02', 'ACTIVE'),
(3, 3, 'ROG-STRIX-PC001', '2026-10-03', '2029-10-03', 'ACTIVE'),
(4, 4, 'DELL-XPS-11001', '2026-10-04', '2027-10-04', 'ACTIVE'),
(5, 5, 'IP15PM-88291001', '2026-10-05', '2027-10-05', 'ACTIVE'),
(6, 6, 'HP-NS1000-77101', '2026-10-06', '2027-10-06', 'ACTIVE'),
(7, 7, 'HIK-4MP-33201', '2026-10-07', '2028-10-07', 'ACTIVE'),
(8, 8, 'DELL-PC3020-5511', '2026-10-08', '2027-10-08', 'ACTIVE'),
(9, 9, 'LOGI-BRIO-4K-01', '2026-10-09', '2028-10-09', 'ACTIVE'),
(10, 10, 'S24U-7761001', '2026-10-09', '2027-10-09', 'ACTIVE');