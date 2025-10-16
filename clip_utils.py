# clip_utils.py
import os
import logging
import hashlib
from typing import List, Optional, Dict, Union
import torch
import clip
from PIL import Image
import clip as openai_clip
import numpy as np
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

class CLIPManager:
    """Handles CLIP model for image and text embeddings"""
    
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.preprocess = None
        self._load_model()
    
    def _load_model(self):
        """Load CLIP model"""
        try:
            logger.info(f"Loading CLIP model on {self.device}...")
            self.model, self.preprocess = openai_clip.load("ViT-B/32", device=self.device)
            logger.info("CLIP model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise
    
    def get_text_embedding(self, text: str) -> List[float]:
        """Get text embedding using CLIP"""
        try:
            with torch.no_grad():
                text_tokens = openai_clip.tokenize([text]).to(self.device)
                text_features = self.model.encode_text(text_tokens)
                text_features = text_features.cpu().numpy().tolist()[0]
                
                # Normalize the embedding
                text_features = np.array(text_features)
                text_features = text_features / np.linalg.norm(text_features)
                
                return text_features.tolist()
        except Exception as e:
            logger.error(f"Error getting text embedding: {e}")
            return [0.0] * 512  # CLIP ViT-B/32 default dimension
    
    def get_image_embedding(self, image_data: Union[str, bytes, Image.Image]) -> List[float]:
        """Get image embedding using CLIP"""
        try:
            # Handle different image input types
            if isinstance(image_data, str):
                # Base64 encoded image
                if image_data.startswith('data:image'):
                    # Remove data URL prefix
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes))
            elif isinstance(image_data, bytes):
                image = Image.open(BytesIO(image_data))
            elif isinstance(image_data, Image.Image):
                image = image_data
            else:
                raise ValueError("Unsupported image data type")
            
            # Preprocess image
            image_input = self.preprocess(image).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                image_features = self.model.encode_image(image_input)
                image_features = image_features.cpu().numpy().tolist()[0]
                
                # Normalize the embedding
                image_features = np.array(image_features)
                image_features = image_features / np.linalg.norm(image_features)
                
                return image_features.tolist()
        except Exception as e:
            logger.error(f"Error getting image embedding: {e}")
            return [0.0] * 512  # CLIP ViT-B/32 default dimension
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Compute cosine similarity between two embeddings"""
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Ensure both vectors have the same dimension
            if vec1.shape != vec2.shape:
                logger.error(f"Vector dimension mismatch: {vec1.shape} vs {vec2.shape}")
                return 0.0
            
            # Compute cosine similarity
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            return float(similarity)
        except Exception as e:
            logger.error(f"Error computing similarity: {e}")
            return 0.0

# Global instance
clip_manager = CLIPManager()