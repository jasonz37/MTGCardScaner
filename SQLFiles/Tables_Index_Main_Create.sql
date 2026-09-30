USE MTGCardScanner;
GO

CREATE TABLE Sets
(
    SetCode NVARCHAR(20) NOT NULL,
    SetName NVARCHAR(200) NOT NULL,
    SetType NVARCHAR(50) NULL,
    ReleaseDate DATE NULL,
    CONSTRAINT PK_Sets
        PRIMARY KEY (SetCode)
);
GO

CREATE TABLE Cards
(
    CardId INT IDENTITY(1,1) NOT NULL,
    OracleId VARCHAR(36) NULL,
    Name NVARCHAR(300) NOT NULL,
    ManaCost NVARCHAR(200) NULL,
    ManaValue DECIMAL(18,2) NULL,
    TypeLine NVARCHAR(500) NULL,
    OracleText NVARCHAR(MAX) NULL,
    Power NVARCHAR(20) NULL,
    Toughness NVARCHAR(20) NULL,
    Loyalty NVARCHAR(20) NULL,
    Colors NVARCHAR(50) NULL,
    ColorIdentity NVARCHAR(50) NULL,
    CONSTRAINT PK_Cards
        PRIMARY KEY (CardId)


);
GO

CREATE TABLE Printings
(
    PrintingId INT IDENTITY(1,1) NOT NULL,
    ScryfallId VARCHAR(36) NOT NULL,
    CardId INT NOT NULL,
    SetCode NVARCHAR(20) NOT NULL,
    CollectorNumber NVARCHAR(50) NULL,
    Rarity NVARCHAR(30) NULL,
    Artist NVARCHAR(200) NULL,
    ReleasedAt DATE NULL,
    LanguageCode NVARCHAR(20) NULL,
    Finish NVARCHAR(100) NULL,
    BorderColor NVARCHAR(30) NULL,
    Frame NVARCHAR(30) NULL,
    FullArt BIT NULL,
    Textless BIT NULL,
    Promo BIT NULL,
    CONSTRAINT PK_Printings
        PRIMARY KEY (PrintingId),

    CONSTRAINT UQ_Printings_ScryfallId
        UNIQUE (ScryfallId),

    CONSTRAINT FK_Printings_Cards
        FOREIGN KEY (CardId)
        REFERENCES Cards(CardId),

    CONSTRAINT FK_Printings_Sets
        FOREIGN KEY (SetCode)
        REFERENCES Sets(SetCode)
);
GO

CREATE TABLE CardImages
(
    ImageId INT IDENTITY(1,1) NOT NULL,
    PrintingId INT NOT NULL,
    ImageType NVARCHAR(30) NOT NULL,
    ImageUrl NVARCHAR(1000) NOT NULL,
    LocalImagePath NVARCHAR(1000) NULL,
    CONSTRAINT PK_CardImages
        PRIMARY KEY (ImageId),

    CONSTRAINT FK_CardImages_Printings
        FOREIGN KEY (PrintingId)
        REFERENCES Printings(PrintingId)
);
GO


CREATE TABLE CardFaces
(
    FaceId INT IDENTITY(1,1) NOT NULL,
    PrintingId INT NOT NULL,
    FaceIndex INT NOT NULL,
    FaceName NVARCHAR(300) NULL,
    ManaCost NVARCHAR(200) NULL,
    TypeLine NVARCHAR(500) NULL,
    OracleText NVARCHAR(MAX) NULL,
    Power NVARCHAR(20) NULL,
    Toughness NVARCHAR(20) NULL,
    Loyalty NVARCHAR(20) NULL,
    ImageUrl NVARCHAR(1000) NULL,
    CONSTRAINT PK_CardFaces
        PRIMARY KEY (FaceId),

    CONSTRAINT FK_CardFaces_Printings
        FOREIGN KEY (PrintingId)
        REFERENCES Printings(PrintingId),

    CONSTRAINT UQ_CardFaces_PrintingFace
        UNIQUE (PrintingId, FaceIndex)
);
GO

CREATE INDEX IX_Cards_Name
ON Cards(Name);
GO

CREATE INDEX IX_Printings_SetCode
ON Printings(SetCode);
GO

CREATE INDEX IX_Printings_CollectorNumber
ON Printings(CollectorNumber);
GO

CREATE INDEX IX_Printings_CardId
ON Printings(CardId);
GO

CREATE INDEX IX_CardFaces_PrintingId
ON CardFaces(PrintingId);
GO

CREATE UNIQUE INDEX UQ_Cards_OracleId
ON Cards (OracleId)
WHERE OracleId IS NOT NULL;
GO
