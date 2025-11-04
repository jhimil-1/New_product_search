#!/usr/bin/env python3
"""
Enhanced Product Handler with improved search relevance
"""

print("ENHANCED_PRODUCT_HANDLER MODULE LOADED")

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class EnhancedProductHandler:
    """Enhanced product handler with semantic relevance filtering"""
    
    def __init__(self, product_handler):
        """Initialize with existing product handler"""
        self.product_handler = product_handler
        self.db = product_handler.db
        self.min_relevance_score = 0.7  # Higher threshold for relevance
        
    def calculate_semantic_relevance(self, query: str, product: Dict[str, Any]) -> float:
        """
        Calculate semantic relevance score between query and product
        Returns score from 0.0 to 1.0
        """
        query_lower = query.lower().strip()
        product_name = product.get('name', '').lower()
        product_desc = product.get('description', '').lower()
        product_category = product.get('category', '').lower()
        
        # Debug output for typo testing
        if query_lower in ['chlothes', 'jeens', 'pents']:
            print(f"DEBUG SEMANTIC: Calculating relevance for query '{query_lower}' on product '{product_name}' in category '{product_category}'")
        
        # Handle typos and misspellings with fuzzy matching
        def fuzzy_match_score(query_word: str, target_word: str) -> float:
            """Calculate fuzzy match score between two words"""
            if query_word == target_word:
                return 1.0
            
            # Debug for specific typos
            if query_word in ['chlothes', 'jeens', 'pents']:
                print(f"DEBUG FUZZY: Comparing '{query_word}' with '{target_word}'")
            
            # Check for common typos and misspellings
            # Common letter substitutions and transpositions
            if abs(len(query_word) - len(target_word)) <= 2:  # Allow 1-2 character difference
                # Check for transposed letters (e.g., "chlothes" vs "clothes")
                if len(query_word) == len(target_word):
                    transpositions = sum(1 for i in range(len(query_word)) 
                                       if query_word[i] != target_word[i])
                    if transpositions <= 2:  # Allow up to 2 transpositions
                        # Special handling for common transpositions like "ch" -> "hc"
                        if (query_word == 'chlothes' and target_word == 'clothes') or \
                           (query_word == 'clohtes' and target_word == 'clothes'):
                            score = 0.85  # High score for this specific common transposition
                        else:
                            score = max(0.7, 1.0 - (transpositions * 0.15))
                        if query_word in ['chlothes', 'jeens', 'pents']:
                            print(f"DEBUG FUZZY: Transposition match! Score: {score}")
                        return score
                
                # Check for missing/extra letters (e.g., "clothess" vs "clothes")
                shorter, longer = sorted([query_word, target_word], key=len)
                if longer.startswith(shorter) or longer.endswith(shorter):
                    if query_word in ['chlothes', 'jeens', 'pents']:
                        print(f"DEBUG FUZZY: Prefix/suffix match! Score: 0.8")
                    return 0.8
                
                # Special handling for common vowel substitutions
                if (query_word == 'jeens' and target_word == 'jeans') or \
                   (query_word == 'pents' and target_word == 'pants') or \
                   (query_word == 'shrit' and target_word == 'shirt') or \
                   (query_word == 'chlothes' and target_word == 'clothes') or \
                   (query_word == 'clotes' and target_word == 'clothes'):
                    if query_word in ['chlothes', 'jeens', 'pents']:
                        print(f"DEBUG FUZZY: Common typo match! Score: 0.8")
                    return 0.8
                
                # Check for common letter substitutions (e.g., 'i' vs 'l', 'o' vs 'e')
                common_substitutions = {
                    'i': ['l', 'j'], 'l': ['i', '1'], 'o': ['e', 'a', '0'],
                    'e': ['o', 'a'], 'a': ['e', 'o'], 's': ['c', 'z'],
                    'c': ['s', 'k'], 'k': ['c'], 't': ['f'], 'f': ['t'],
                    'u': ['o'], 'o': ['u'], 'n': ['m'], 'm': ['n']
                }
                
                # Check for vowel substitutions (e.g., "jeens" vs "jeans")
                vowel_substitutions = {
                    'a': ['e', 'i', 'o', 'u'], 'e': ['a', 'i', 'o', 'u'],
                    'i': ['a', 'e', 'o', 'u'], 'o': ['a', 'e', 'i', 'u'],
                    'u': ['a', 'e', 'i', 'o']
                }
                
                # Calculate character-level similarity
                differences = 0
                max_len = max(len(query_word), len(target_word))
                min_len = min(len(query_word), len(target_word))
                
                # Check character by character
                for i in range(min_len):
                    q_char = query_word[i] if i < len(query_word) else ''
                    t_char = target_word[i] if i < len(target_word) else ''
                    
                    if q_char != t_char:
                        # Check for common substitutions
                        if (q_char in common_substitutions and 
                            t_char in common_substitutions[q_char]):
                            differences += 0.5  # Half penalty for common substitutions
                        # Check for vowel substitutions
                        elif (q_char in vowel_substitutions and 
                              t_char in vowel_substitutions[q_char]):
                            differences += 0.3  # Lower penalty for vowel substitutions
                        else:
                            differences += 1  # Full penalty for other differences
                
                # Account for length difference
                differences += abs(len(query_word) - len(target_word))
                
                # Calculate similarity score
                similarity = 1.0 - (differences / max_len)
                
                if query_word in ['chlothes', 'jeens', 'pents']:
                    print(f"DEBUG FUZZY: Character similarity: {similarity} (differences: {differences}, max_len: {max_len})")
                
                if similarity >= 0.6:  # At least 60% similar
                    return similarity
            
            return 0.0
        
        # Handle broad/generic queries like "products", "items", "goods"
        broad_terms = ['products', 'items', 'goods', 'merchandise', 'stuff']
        
        # Check for broad terms with fuzzy matching
        broad_match_score = 0.0
        for broad_term in broad_terms:
            fuzzy_score = fuzzy_match_score(query_lower, broad_term)
            if fuzzy_score > 0.7:  # High fuzzy match threshold for broad terms
                broad_match_score = max(broad_match_score, fuzzy_score)
        
        if broad_match_score > 0.7:
            # For broad queries, give a base relevance score to all products
            base_score = 0.4  # Base score for broad queries
            
            # Slight boost for products in the same category as recent searches or common categories
            if product_category in ['electronics', 'clothing', 'jewelry']:
                base_score += 0.1
            
            # Slight boost for products with good descriptions
            if len(product_desc) > 20:
                base_score += 0.05
            
            return min(base_score, 0.6)  # Cap broad query scores
        
        # Enhanced matching with fuzzy support
        def fuzzy_contains(query_text: str, target_text: str) -> float:
            """Check if query is contained in target with fuzzy matching"""
            if query_text in target_text:
                return 1.0
            
            # Try fuzzy matching for single words
            if ' ' not in query_text and ' ' not in target_text:
                return fuzzy_match_score(query_text, target_text)
            
            # For multi-word queries, try fuzzy matching each word
            query_words = query_text.split()
            target_words = target_text.split()
            
            total_score = 0.0
            for q_word in query_words:
                best_match = 0.0
                for t_word in target_words:
                    match_score = fuzzy_match_score(q_word, t_word)
                    best_match = max(best_match, match_score)
                total_score += best_match
            
            return total_score / max(len(query_words), 1)
        
        # Enhanced exact match bonuses with fuzzy support
        exact_name_match = fuzzy_contains(query_lower, product_name) > 0.8
        exact_desc_match = fuzzy_contains(query_lower, product_desc) > 0.8
        exact_category_match = fuzzy_contains(query_lower, product_category) > 0.8
        
        # Word-level matching with fuzzy support
        query_words = query_lower.split()
        name_words = product_name.split()
        desc_words = product_desc.split()
        category_words = product_category.split()
        
        # Calculate fuzzy word overlap
        name_overlap = 0.0
        desc_overlap = 0.0
        category_overlap = 0.0
        
        # Fuzzy intersection for name words
        for q_word in query_words:
            best_match = 0.0
            for n_word in name_words:
                match_score = fuzzy_match_score(q_word, n_word)
                best_match = max(best_match, match_score)
            name_overlap += best_match
        name_overlap = name_overlap / max(len(query_words), 1)
        
        # Fuzzy intersection for description words
        for q_word in query_words:
            best_match = 0.0
            for d_word in desc_words:
                match_score = fuzzy_match_score(q_word, d_word)
                best_match = max(best_match, match_score)
            desc_overlap += best_match
        desc_overlap = desc_overlap / max(len(query_words), 1)
        
        # Fuzzy intersection for category words
        for q_word in query_words:
            best_match = 0.0
            for c_word in category_words:
                match_score = fuzzy_match_score(q_word, c_word)
                best_match = max(best_match, match_score)
            category_overlap += best_match
        category_overlap = category_overlap / max(len(query_words), 1)
        
        # Category-specific relevance scoring with fuzzy support
        def get_fuzzy_category_score(query_keyword: str, product_cat: str) -> float:
            """Get category score with fuzzy matching for keywords"""
            # Common clothing terms with their fuzzy variations
            clothing_variations = {
                'clothes': ['clothes', 'clothing', 'cloths', 'chlothes', 'clohtes', 'clotes', 'clothess', 'cloaths', 'clothez'],
                'pant': ['pant', 'pants', 'jeans', 'trousers', 'joggers', 'leggings', 'shorts', 'pents'],
                'jeans': ['jeans', 'denim', 'pants', 'trousers', 'jeens', 'jens'],
                'dress': ['dress', 'gown', 'frock', 'outfit', 'dresss'],
                'shirt': ['shirt', 'top', 'blouse', 't-shirt', 'tee', 'shrit', 'shrits'],
                'apparel': ['apparel', 'garment', 'wear', 'fashion', 'apparell']
            }
            
            # Check if query keyword matches any clothing variation
            for base_term, variations in clothing_variations.items():
                for variation in variations:
                    if fuzzy_match_score(query_keyword, variation) > 0.8:
                        # Map to standard category scores
                        if base_term == 'clothes':
                            return {'clothing': 1.0, 'clothes': 1.0, 'apparel': 1.0, 'garment': 1.0, 'wear': 0.9, 'fashion': 0.8}.get(product_cat, 0.0)
                        elif base_term == 'pant':
                            return {'clothing': 1.0, 'pants': 1.0, 'jeans': 1.0, 'trousers': 1.0, 'joggers': 0.9, 'leggings': 0.8, 'shorts': 0.7}.get(product_cat, 0.0)
                        elif base_term == 'jeans':
                            return {'clothing': 1.0, 'pants': 1.0, 'jeans': 1.0, 'trousers': 1.0, 'denim': 1.0, 'joggers': 0.8, 'leggings': 0.7}.get(product_cat, 0.0)
                        elif base_term == 'dress':
                            return {'clothing': 1.0, 'dress': 1.0, 'gown': 1.0, 'frock': 1.0, 'apparel': 0.9, 'garment': 0.8}.get(product_cat, 0.0)
                        elif base_term == 'shirt':
                            return {'clothing': 1.0, 'shirt': 1.0, 'top': 1.0, 'blouse': 1.0, 'apparel': 0.9, 'garment': 0.8, 't-shirt': 1.0, 'tee': 0.9}.get(product_cat, 0.0)
                        elif base_term == 'apparel':
                            return {'clothing': 1.0, 'clothes': 1.0, 'apparel': 1.0, 'garment': 1.0, 'wear': 0.9, 'fashion': 0.8}.get(product_cat, 0.0)
            
            return 0.0
        
        category_scores = {
            'pant': {
                'clothing': 1.0, 'pants': 1.0, 'jeans': 1.0, 'trousers': 1.0,
                'joggers': 0.9, 'leggings': 0.8, 'shorts': 0.7
            },
            'jeans': {
                'clothing': 1.0, 'pants': 1.0, 'jeans': 1.0, 'trousers': 1.0,
                'denim': 1.0, 'joggers': 0.8, 'leggings': 0.7
            },
            'dress': {
                'clothing': 1.0, 'dress': 1.0, 'gown': 1.0, 'frock': 1.0,
                'apparel': 0.9, 'garment': 0.8
            },
            'shirt': {
                'clothing': 1.0, 'shirt': 1.0, 'top': 1.0, 'blouse': 1.0,
                'apparel': 0.9, 'garment': 0.8, 't-shirt': 1.0, 'tee': 0.9
            },
            'clothes': {
                'clothing': 1.0, 'clothes': 1.0, 'apparel': 1.0, 'garment': 1.0,
                'wear': 0.9, 'fashion': 0.8
            },
            'clothing': {
                'clothing': 1.0, 'clothes': 1.0, 'apparel': 1.0, 'garment': 1.0,
                'wear': 0.9, 'fashion': 0.8
            },
            'smartphone': {
                'electronics': 1.0, 'phone': 1.0, 'smartphone': 1.0, 'mobile': 1.0
            },
            'phone': {
                'electronics': 1.0, 'phone': 1.0, 'smartphone': 1.0, 'mobile': 1.0,
                'camera': 0.8, 'webcam': 0.7, 'dash cam': 0.6
            },
            'headphones': {
                'electronics': 1.0, 'headphones': 1.0, 'headphone': 1.0, 'earbuds': 1.0, 'earphone': 1.0,
                'audio': 0.9, 'wireless': 0.8, 'bluetooth': 0.8, 'noise cancelling': 0.9
            },
            'electronics': {
                'electronics': 1.0, 'electronic': 1.0, 'tech': 0.9, 'gadget': 0.9,
                'smart': 0.8, 'digital': 0.8, 'wifi': 0.7, 'bluetooth': 0.7
            },
            'jewelry': {
                'jewelry': 1.0, 'jewellery': 1.0, 'earrings': 1.0, 'necklace': 1.0, 
                'bracelet': 1.0, 'ring': 1.0, 'watch': 0.8, 'pendant': 1.0, 
                'chain': 0.9, 'accessories': 0.7
            },
            'jewellery': {
                'jewelry': 1.0, 'jewellery': 1.0, 'jewellry': 1.0, 'earrings': 1.0, 
                'necklace': 1.0, 'bracelet': 1.0, 'ring': 1.0, 'watch': 0.8, 'pendant': 1.0, 
                'chain': 0.9, 'accessories': 0.7
            }
        }
        
        # Base relevance score
        relevance_score = 0.0
        
        # Exact matches get highest scores
        if exact_name_match:
            relevance_score += 0.8
        if exact_desc_match:
            relevance_score += 0.4
        if exact_category_match:
            relevance_score += 0.3
            
        # Word overlap scores
        relevance_score += name_overlap * 0.6
        relevance_score += desc_overlap * 0.3
        relevance_score += category_overlap * 0.2
        
        # Category-specific scoring with fuzzy support
        # Special handling for headphones - check this first to avoid conflicts
        if 'headphones' in query_lower or 'headphone' in query_lower or 'earbuds' in query_lower or 'earphone' in query_lower:
            product_cat = product_category.lower()
            if product_cat == 'electronics':
                # Only give bonus if product name contains headphones-related terms
                product_name_lower = product.get('name', '').lower()
                if any(term in product_name_lower for term in ['headphone', 'earbuds', 'earphone']):
                    relevance_score += 0.5  # Full bonus for actual headphones
                    if 'headphones' in query_lower:
                        print(f"DEBUG SEMANTIC: Headphones product found! Adding 0.5 bonus")
                else:
                    # NO bonus for other electronics when searching for headphones
                    if 'headphones' in query_lower:
                        print(f"DEBUG SEMANTIC: Non-headphones electronics, adding 0.0 bonus")
                    relevance_score += 0.0
            elif 'clothing' in product_cat:
                relevance_score += 0.3  # General clothing bonus
                if 'headphones' in query_lower:
                    print(f"DEBUG SEMANTIC: Clothing bonus: 0.3")
        else:
            # Enhanced category scoring with fuzzy support for clothing queries
            clothing_keywords = ['clothes', 'clothing', 'shirt', 'dress', 'pants', 'jeans', 'top', 'blouse']
            is_clothing_query = False
            
            # Check for clothing keywords with fuzzy matching
            for clothing_keyword in clothing_keywords:
                fuzzy_clothing_score = fuzzy_match_score(query_lower, clothing_keyword)
                if fuzzy_clothing_score > 0.8:
                    is_clothing_query = True
                    print(f"DEBUG SEMANTIC: Clothing query detected! '{query_lower}' matches '{clothing_keyword}' with score {fuzzy_clothing_score}")
                    break
            
            # Use fuzzy category scoring for clothing terms
            query_words = query_lower.split()
            for keyword in category_scores.keys():
                # Check if any query word matches this keyword with fuzzy matching
                for query_word in query_words:
                    fuzzy_word_score = fuzzy_match_score(query_word, keyword)
                    if fuzzy_word_score > 0.5:  # Lower threshold for single words
                        product_cat = product_category.lower()
                        fuzzy_score = get_fuzzy_category_score(keyword, product_cat)
                        if fuzzy_score > 0:
                            relevance_score += fuzzy_score * 0.5
                            print(f"DEBUG SEMANTIC: Fuzzy category bonus for '{query_word}' -> '{keyword}': {fuzzy_score * 0.5}")
                        break  # Only count each keyword once
            
            # Apply enhanced clothing bonus for clothing queries on clothing products
            if is_clothing_query and ('clothing' in product_category.lower() or 'clothes' in product_category.lower()):
                print(f"DEBUG SEMANTIC: Base relevance score before clothing bonus: {relevance_score}")
                relevance_score += 0.4  # Enhanced clothing bonus for clothing queries
                print(f"DEBUG SEMANTIC: Enhanced clothing bonus for '{query_lower}' on clothing product '{product_name}': 0.4")
                print(f"DEBUG SEMANTIC: Relevance score after clothing bonus: {relevance_score}")
                    
        # Penalize obviously wrong categories (but be more lenient on broad terms)
        wrong_category_penalties = {
            'pant': ['electronics', 'home', 'kitchen', 'appliance'],
            'dress': ['electronics', 'home', 'kitchen', 'appliance'],
            'shirt': ['electronics', 'home', 'kitchen', 'appliance'],
            'smartphone': ['clothing', 'jewelry', 'home', 'kitchen'],
            'phone': ['clothing', 'jewelry', 'home', 'kitchen']
        }
        
        # Don't penalize broad electronics queries as harshly
        if any(broad_term in query_lower for broad_term in ['electronics', 'tech', 'gadget']):
            penalty_weight = 0.2  # Lighter penalty for broad terms
        else:
            penalty_weight = 0.5  # Standard penalty for specific mismatches
            
        for keyword, wrong_cats in wrong_category_penalties.items():
            if keyword in query_lower and product_category in wrong_cats:
                relevance_score -= penalty_weight  # Adjusted penalty for wrong category
                
        print(f"DEBUG SEMANTIC: Final relevance score for '{product_name}' (category: {product_category}): {relevance_score}")
        
        return min(relevance_score, 1.0)  # Cap at 1.0
    
    def filter_irrelevant_results(self, query: str, products: List[Dict[str, Any]], 
                                 min_semantic_score: float = None) -> List[Dict[str, Any]]:
        """
        Filter out irrelevant products based on semantic analysis
        """
        print(f"FILTER: Starting filter_irrelevant_results with query: '{query}', products: {len(products)}, min_semantic_score: {min_semantic_score}")
        
        if not query or not products:
            print(f"FILTER: Returning early - query empty: {not query}, products empty: {not products}")
            return products
        
        # Set default minimum semantic score based on query type
        query_lower = query.lower()
        print(f"DEBUG: Setting min_semantic_score for query: '{query}' (lower: '{query_lower}')")
        print(f"DEBUG: Checking headphones words in query: 'headphones' in '{query_lower}' = {'headphones' in query_lower}")
        print(f"DEBUG: Checking headphones words in query: 'headphone' in '{query_lower}' = {'headphone' in query_lower}")
        print(f"DEBUG: Checking headphones words in query: 'earbuds' in '{query_lower}' = {'earbuds' in query_lower}")
        print(f"DEBUG: Checking headphones words in query: 'earphone' in '{query_lower}' = {'earphone' in query_lower}")
        
        if min_semantic_score is None:
            # Special handling for specific product queries
            headphones_words = ['headphones', 'headphone', 'earbuds', 'earphone']
            if any(word in query_lower for word in headphones_words):
                # For headphones queries, require higher semantic relevance to avoid showing other electronics
                min_semantic_score = 0.8  # Very high threshold - only allow actual headphones with very high semantic scores
                print(f"DEBUG: Headphones detected! Words found: {[word for word in headphones_words if word in query_lower]}")
            elif any(word in query_lower for word in ['phone', 'smartphone', 'mobile', 'cell', 'telephone']):
                # For specific phone queries, be more lenient with electronics but still filter obvious mismatches
                min_semantic_score = 0.05  # Very low threshold - mainly filter by vector score
                print(f"DEBUG: Phone detected, setting min_semantic_score to 0.05")
            elif any(word in query_lower for word in ['electronics', 'tech', 'gadget']):
                # For broad electronics queries, be quite lenient
                min_semantic_score = 0.02  # Very low threshold for broad electronics
                print(f"DEBUG: Electronics detected, setting min_semantic_score to 0.02")
            elif any(word in query_lower for word in ['jewelry', 'jewellery', 'necklace', 'earrings', 'bracelet', 'ring']):
                # For jewelry queries, be more strict about category matching
                min_semantic_score = 0.4
                print(f"DEBUG: Jewelry detected, setting min_semantic_score to 0.4")
            elif any(word in query_lower for word in ['products', 'items', 'goods', 'merchandise', 'stuff']):
                # For very broad/generic queries, be extremely lenient - rely mainly on vector similarity
                min_semantic_score = 0.01  # Almost no semantic filtering for broad terms
                print(f"DEBUG: Broad/generic query detected, setting min_semantic_score to 0.01")
            else:
                # Default threshold for general queries
                min_semantic_score = 0.3
                print(f"DEBUG: General query detected, setting min_semantic_score to 0.3")
        
        print(f"FILTER: Using min_semantic_score = {min_semantic_score}")
        
        filtered_products = []
        
        for i, product in enumerate(products):
            # Calculate semantic relevance score
            semantic_score = self.calculate_semantic_relevance(query, product)
            
            print(f"FILTER: Product {i+1}: '{product.get('name', 'Unknown')}' - semantic score: {semantic_score:.3f}")
            
            # Add debug output for headphones
            if 'headphones' in query_lower:
                print(f"DEBUG FILTER: Product '{product.get('name', '')}' has semantic score: {semantic_score}")
            
            # Only keep products that meet the minimum semantic relevance threshold
            if semantic_score >= min_semantic_score:
                # Add the relevance score to the product for debugging
                if 'search_metadata' not in product:
                    product['search_metadata'] = {}
                product['search_metadata']['semantic_relevance_score'] = semantic_score
                filtered_products.append(product)
                
                # Debug output for headphones
                if 'headphones' in query_lower:
                    print(f"DEBUG FILTER: Product KEPT - meets threshold")
            else:
                # Debug output for headphones
                if 'headphones' in query_lower:
                    print(f"DEBUG FILTER: Product FILTERED OUT - score {semantic_score} < threshold {min_semantic_score}")
        
        print(f"FILTER: {len(filtered_products)} products kept out of {len(products)} total")
        if 'headphones' in query_lower:
            print(f"DEBUG FILTER: Final count: {len(filtered_products)} products")
        
        return filtered_products
    
    async def search_products(self, query: str, user_id: str = None, category: str = None, 
                             min_relevance_score: float = 0.0, limit: int = 20, 
                             search_type: str = "text", image_data: bytes = None,
                             min_semantic_score: float = None) -> Dict[str, Any]:
        """
        Enhanced search with semantic relevance filtering
        """
        print(f"ENHANCED_SEARCH: Starting search for query: '{query}'")
        print(f"ENHANCED_SEARCH: Parameters - user_id: {user_id}, category: {category}, min_relevance_score: {min_relevance_score}")
        print(f"ENHANCED_SEARCH: limit: {limit}, search_type: {search_type}, min_semantic_score: {min_semantic_score}")
        
        # Perform the base search using the original product handler
        if search_type == "text":
            base_results = await self.product_handler.search_products(
                query=query, 
                user_id=user_id, 
                category=category, 
                min_score=min_relevance_score, 
                limit=limit
            )
        elif search_type == "image":
            # For image search, use the image search method
            base_results = await self.product_handler.search_products(
                query=query, 
                user_id=user_id, 
                category=category, 
                min_score=min_relevance_score, 
                limit=limit,
                image_bytes=image_data
            )
        else:
            # Fallback to text search
            base_results = await self.product_handler.search_products(
                query=query, 
                user_id=user_id, 
                category=category, 
                min_score=min_relevance_score, 
                limit=limit
            )
        
        print(f"ENHANCED_SEARCH: Base search returned {len(base_results.get('products', base_results.get('results', [])))} products")
        
        # Apply semantic relevance filtering
        products = base_results.get('products', base_results.get('results', []))
        
        if products:
            print(f"ENHANCED_SEARCH: Applying semantic filtering to {len(products)} products")
            print(f"ENHANCED_SEARCH: Query for semantic filtering: '{query}'")
            print(f"ENHANCED_SEARCH: Min semantic score: {min_semantic_score}")
            filtered_products = self.filter_irrelevant_results(query, products, min_semantic_score)
            print(f"ENHANCED_SEARCH: Semantic filtering kept {len(filtered_products)} products")
            
            # Update the results with filtered products
            base_results['products'] = filtered_products
            base_results['total_found'] = len(filtered_products)
            
            # Add enhanced metadata
            if 'search_metadata' not in base_results:
                base_results['search_metadata'] = {}
            
            base_results['search_metadata']['semantic_filtering_applied'] = True
            base_results['search_metadata']['original_count'] = len(products)
            base_results['search_metadata']['filtered_count'] = len(filtered_products)
            base_results['search_metadata']['min_semantic_score_used'] = min_semantic_score or self.min_relevance_score
        
        print(f"ENHANCED_SEARCH: Final result contains {len(base_results.get('products', []))} products")
        return base_results
    
    async def search_jewelry_by_image_and_category(self, image_data: bytes, category: str, 
                                                   user_id: str = None, limit: int = 20,
                                                   min_relevance_score: float = 0.0) -> Dict[str, Any]:
        """
        Specialized method for jewelry image search with category filtering
        """
        print(f"JEWELRY_IMAGE_SEARCH: Starting jewelry image search for category: '{category}'")
        
        # Use the base image search with jewelry-specific parameters
        results = await self.search_products(
            query=f"jewelry {category}",  # Enhanced query for jewelry
            user_id=user_id,
            category=category,
            min_relevance_score=min_relevance_score,
            limit=limit,
            search_type="image",
            image_data=image_data,
            min_semantic_score=0.4  # Higher semantic threshold for jewelry
        )
        
        # Add jewelry-specific metadata
        if 'search_metadata' not in results:
            results['search_metadata'] = {}
        
        results['search_metadata']['jewelry_search'] = True
        results['search_metadata']['category_filter'] = category
        
        print(f"JEWELRY_IMAGE_SEARCH: Found {len(results.get('products', []))} jewelry items")
        return results
    
    async def search_products_enhanced(self, query: str, user_id: str = None, 
                                   category: str = None, limit: int = 20,
                                   min_relevance_score: float = 0.0,
                                   min_semantic_score: float = None) -> Dict[str, Any]:
        """
        Enhanced search method that the chatbot expects to call.
        This is a wrapper around search_products for backward compatibility.
        """
        print(f"SEARCH_PRODUCTS_ENHANCED: Starting enhanced search for query: '{query}'")
        print(f"SEARCH_PRODUCTS_ENHANCED: Parameters - user_id: {user_id}, category: {category}, limit: {limit}")
        print(f"SEARCH_PRODUCTS_ENHANCED: min_relevance_score: {min_relevance_score}")
        
        # Try with the provided category first
        results = await self.search_products(
            query=query,
            user_id=user_id,
            category=category,
            min_relevance_score=min_relevance_score,
            limit=limit,
            search_type="text",
            min_semantic_score=min_semantic_score
        )
        
        # If no results and category was provided, try category variations
        if len(results.get('products', [])) == 0 and category:
            print(f"SEARCH_PRODUCTS_ENHANCED: No results with category '{category}', trying variations...")
            
            # Define category variations for common misspellings
            category_variations = []
            if category.lower() == 'jewelry':
                category_variations = ['Jewellery', 'jewellery', 'JEWELRY']
            elif category.lower() == 'jewellery':
                category_variations = ['Jewelry', 'jewelry', 'JEWELLERY']
            elif category.lower() == 'clothing':
                category_variations = ['Clothes', 'clothes', 'CLOTHING']
            elif category.lower() == 'clothes':
                category_variations = ['Clothing', 'clothing', 'CLOTHES']
            elif category.lower() == 'electronics':
                category_variations = ['Electronics', 'ELECTRONICS']
            
            # Try each variation
            for variation in category_variations:
                print(f"SEARCH_PRODUCTS_ENHANCED: Trying category variation: '{variation}'")
                results = await self.search_products(
                    query=query,
                    user_id=user_id,
                    category=variation,
                    min_relevance_score=min_relevance_score,
                    limit=limit,
                    search_type="text",
                    min_semantic_score=min_semantic_score
                )
                if len(results.get('products', [])) > 0:
                    print(f"SEARCH_PRODUCTS_ENHANCED: Found results with category variation: '{variation}'")
                    break
            
            # If still no results, try without category filter
            if len(results.get('products', [])) == 0:
                print(f"SEARCH_PRODUCTS_ENHANCED: No results with category variations, trying without category filter...")
                results = await self.search_products(
                    query=query,
                    user_id=user_id,
                    category=None,
                    min_relevance_score=min_relevance_score,
                    limit=limit,
                    search_type="text",
                    min_semantic_score=min_semantic_score
                )
        
        print(f"SEARCH_PRODUCTS_ENHANCED: Found {len(results.get('products', []))} products")
        return results