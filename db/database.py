"""
Database connection management and schema initialization
Supports SQLite with upgrade path to Azure SQL
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiosqlite


class DatabaseManager:
    """Manages database connections and schema operations"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.logger = logging.getLogger(__name__)
        self._connection: Optional[aiosqlite.Connection] = None
        
        # Parse database URL to determine type
        parsed = urlparse(database_url)
        self.db_type = parsed.scheme.split('+')[0]  # sqlite, mssql, etc.
        
        if self.db_type == 'sqlite':
            # Extract file path from sqlite URL
            self.db_path = database_url.replace('sqlite:///', '')
        else:
            self.db_path = None
    
    async def initialize(self):
        """Initialize database connection and create schema if needed"""
        try:
            if self.db_type == 'sqlite':
                await self._initialize_sqlite()
            else:
                raise NotImplementedError(f"Database type {self.db_type} not yet supported")
            
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _initialize_sqlite(self):
        """Initialize SQLite database"""
        # Ensure directory exists
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create connection
        self._connection = await aiosqlite.connect(self.db_path or ':memory:')
        
        # Enable foreign key constraints
        await self._connection.execute("PRAGMA foreign_keys = ON")
        
        # Create schema if it doesn't exist
        await self._create_schema()
        
        # Apply any pending migrations
        await self._apply_migrations()
    
    async def _create_schema(self):
        """Create database schema"""
        schema_sql = """
        -- Recipients table
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'replied', 'stopped')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Email sequence table
        CREATE TABLE IF NOT EXISTS email_sequence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_id INTEGER NOT NULL,
            step INTEGER NOT NULL CHECK (step IN (1, 2, 3)),
            scheduled_at TIMESTAMP NOT NULL,
            sent_at TIMESTAMP NULL,
            message_id TEXT NULL,
            replied BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recipient_id) REFERENCES recipients (id) ON DELETE CASCADE,
            UNIQUE(recipient_id, step)
        );
        
        -- Schema version table for migrations
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_recipients_email ON recipients(email);
        CREATE INDEX IF NOT EXISTS idx_recipients_status ON recipients(status);
        CREATE INDEX IF NOT EXISTS idx_email_sequence_recipient ON email_sequence(recipient_id);
        CREATE INDEX IF NOT EXISTS idx_email_sequence_scheduled ON email_sequence(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_email_sequence_message_id ON email_sequence(message_id);
        CREATE INDEX IF NOT EXISTS idx_email_sequence_replied ON email_sequence(replied);
        """
        
        # Execute schema creation
        await self._connection.executescript(schema_sql)
        await self._connection.commit()
        
        self.logger.info("Database schema created successfully")
    
    async def _apply_migrations(self):
        """Apply database migrations"""
        # Check current schema version
        current_version = await self._get_schema_version()
        
        # Define migrations (version -> SQL)
        migrations = {
            1: """
            -- Initial schema version
            INSERT OR IGNORE INTO schema_version (version) VALUES (1);
            """
        }
        
        # Apply pending migrations
        for version, sql in migrations.items():
            if version > current_version:
                self.logger.info(f"Applying migration version {version}")
                await self._connection.executescript(sql)
                await self._connection.commit()
    
    async def _get_schema_version(self) -> int:
        """Get current schema version"""
        try:
            cursor = await self._connection.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            result = await cursor.fetchone()
            return result[0] if result[0] is not None else 0
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return 0
    
    async def get_connection(self) -> aiosqlite.Connection:
        """Get database connection"""
        if not self._connection:
            await self.initialize()
        return self._connection
    
    async def execute_query(self, query: str, params: tuple = None):
        """Execute a query and return results"""
        connection = await self.get_connection()
        cursor = await connection.execute(query, params or ())
        return await cursor.fetchall()
    
    async def execute_insert(self, query: str, params: tuple = None) -> int:
        """Execute insert query and return last row ID"""
        connection = await self.get_connection()
        cursor = await connection.execute(query, params or ())
        await connection.commit()
        return cursor.lastrowid
    
    async def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute update/delete query and return affected rows"""
        connection = await self.get_connection()
        cursor = await connection.execute(query, params or ())
        await connection.commit()
        return cursor.rowcount
    
    async def close(self):
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self.logger.info("Database connection closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()