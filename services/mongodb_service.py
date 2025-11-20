"""
MongoDB Service for Episode Management

Provides database operations for episodes collection in MongoDB.
"""

import logging
import os
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)


class MongoDBServiceError(Exception):
    """Base exception for MongoDB service errors."""
    pass


class MongoDBConnectionError(MongoDBServiceError):
    """Raised when MongoDB connection fails."""
    pass


class EpisodeNotFoundInDBError(MongoDBServiceError):
    """Raised when episode is not found in database."""
    pass


class MongoDBService:
    """Service for managing MongoDB operations."""

    def __init__(self):
        """
        Initialize MongoDB service.

        Reads connection settings from environment variables:
        - MONGODB_URI: MongoDB connection string
        - MONGODB_DATABASE_NAME: Database name
        """
        self.uri = os.getenv("MONGODB_URI")
        self.database_name = os.getenv("MONGODB_DATABASE_NAME", "dev_lingohow")

        if not self.uri:
            raise MongoDBConnectionError("MONGODB_URI environment variable not set")

        self.client: Optional[MongoClient] = None
        self.db = None

        logger.info(f"MongoDB service initialized with database: {self.database_name}")

    def connect(self):
        """Establish connection to MongoDB."""
        if self.client is None:
            try:
                self.client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000
                )
                # Test the connection
                self.client.admin.command('ping')
                self.db = self.client[self.database_name]
                logger.info(f"✅ Connected to MongoDB database: {self.database_name}")
            except ConnectionFailure as e:
                logger.error(f"❌ Failed to connect to MongoDB: {e}")
                raise MongoDBConnectionError(f"Failed to connect to MongoDB: {e}")
            except Exception as e:
                logger.error(f"❌ Unexpected error connecting to MongoDB: {e}")
                raise MongoDBConnectionError(f"Unexpected error: {e}")

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")

    def get_episode_by_id(self, episode_id: int) -> Dict[str, Any]:
        """
        Get episode data from MongoDB by episode_id.

        Args:
            episode_id: Episode ID to query (will be converted to string for MongoDB query)

        Returns:
            Episode document as dictionary

        Raises:
            EpisodeNotFoundInDBError: If episode is not found
            MongoDBConnectionError: If connection fails
            MongoDBServiceError: For other database errors
        """
        try:
            # Ensure connection is established
            if self.db is None:
                self.connect()

            # Convert episode_id to string for MongoDB query
            # MongoDB stores episode_id as string (e.g., "238", "239")
            episode_id_str = str(episode_id)

            # Query episodes collection
            episodes_collection = self.db["episodes"]
            episode = episodes_collection.find_one({"episode_id": episode_id_str})

            if episode is None:
                raise EpisodeNotFoundInDBError(f"Episode {episode_id} not found in database")

            # Convert ObjectId to string for JSON serialization
            if "_id" in episode:
                episode["_id"] = str(episode["_id"])

            logger.info(f"📖 Retrieved episode {episode_id} (stored as '{episode_id_str}') from MongoDB")
            return episode

        except EpisodeNotFoundInDBError:
            raise
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection error: {e}")
            raise MongoDBConnectionError(f"Connection error: {e}")
        except OperationFailure as e:
            logger.error(f"MongoDB operation error: {e}")
            raise MongoDBServiceError(f"Operation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected MongoDB error: {e}")
            raise MongoDBServiceError(f"Unexpected error: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


__all__ = [
    'MongoDBService',
    'MongoDBServiceError',
    'MongoDBConnectionError',
    'EpisodeNotFoundInDBError'
]
