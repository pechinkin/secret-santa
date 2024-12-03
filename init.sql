CREATE TABLE users (
    nickname VARCHAR(50) PRIMARY KEY,
    password VARCHAR(100) NOT NULL,
    contact_info VARCHAR(255),
    wishes TEXT,
    gifting_to TEXT
);
