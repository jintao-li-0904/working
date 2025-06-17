#!/usr/bin/env python3
"""
Canadian Medical Product Short Name Creation Rules Engine
Fixed version with proper duplicate prevention and dictionary usage
"""

import re
import os
import sys
import json
import argparse
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set, Union
from enum import Enum
from pathlib import Path

# For reading Excel and CSV files
try:
    import pandas as pd
except ImportError:
    print("Please install pandas: pip install pandas openpyxl")
    sys.exit(1)


class Position(Enum):
    """Five-position structure for short descriptions"""
    PRODUCT_TYPE = 1  # Product Type (noun) - Mandatory
    PRODUCT_NAME = 2  # Product Name (adjective/descriptor) - Optional
    PRIMARY_VARIANT = 3  # Primary variant/descriptor - Optional
    SECONDARY_VARIANT = 4  # Secondary variant/descriptor - Optional
    ADDITIONAL_DESCRIPTOR = 5  # Additional descriptor - Optional


@dataclass
class TokenInfo:
    """Information about a parsed token"""
    value: str
    original: str
    token_type: str
    priority: int
    position_hints: List[Position]
    index: int  # Position in original text
    is_used: bool = False


@dataclass
class ShortNameComponent:
    """Represents a component of the short name"""
    position: Position
    value: str
    original_value: str
    is_mandatory: bool = False
    applied_rules: List[str] = field(default_factory=list)
    token_index: int = -1  # Track which token was used


@dataclass
class ShortNameRules:
    """Encapsulates all rules for creating short names"""
    
    # Character limits
    MAX_LENGTH: int = 35
    
    # Position requirements
    MANDATORY_POSITIONS: List[Position] = field(default_factory=lambda: [Position.PRODUCT_TYPE])
    
    # Position 1 should NOT be abbreviated (spell out in full)
    NO_ABBREVIATE_POSITIONS: List[Position] = field(default_factory=lambda: [Position.PRODUCT_TYPE])
    
    # Allowed characters (whitelist approach)
    ALLOWED_CHARS_PATTERN: str = r'^[A-Za-z0-9\s\/\-\+\.\%\(\)]+$'
    
    # Prohibited special characters
    PROHIBITED_CHARS: Set[str] = field(default_factory=lambda: {
        '@', '#', '$', '&', '*', '!', '?', '~', '^', '=', '[', ']', '{', '}',
        '|', '\\', '<', '>', ';', ':', '"', "'", '`', '§', '©', '®', '™',
        '€', '£', '¥', '¢', '°', '±', '×', '÷', '≈', '≠', '≤', '≥',
        '∞', '∑', '∏', '√', '∫', '∂', '∇', 'Δ', 'Ω', 'α', 'β', 'γ', 'δ',
    })
    
    # Prohibited patterns
    PROHIBITED_PATTERNS: List[Tuple[str, str]] = field(default_factory=lambda: [
        (r'\s-\s', "Spaces around hyphens used as separators"),
        (r'-$', "Hyphen at the end"),
        (r'^-', "Hyphen at the beginning"),
        (r'\s\+\s', "Spaces around plus signs"),
        (r'--+', "Multiple consecutive hyphens"),
        (r'//', "Multiple consecutive slashes"),
        (r'\+\+', "Multiple consecutive plus signs"),
        (r'\s{2,}', "Multiple consecutive spaces"),
        (r'[^\x00-\x7F]', "Non-ASCII characters"),
    ])
    
    # Common medical product types (nouns) - expanded list
    PRODUCT_TYPES: Set[str] = field(default_factory=lambda: {
        # Solutions and liquids
        'solution', 'fluid', 'liquid', 'suspension', 'emulsion', 'irrigation',
        # Surgical items
        'suture', 'tape', 'scissor', 'scissors', 'forceps', 'clamp', 'retractor', 
        'scalpel', 'blade', 'knife', 'curette', 'elevator', 'probe',
        # Medical devices
        'needle', 'syringe', 'catheter', 'tube', 'cannula', 'trocar', 'dilator',
        'stent', 'shunt', 'drain', 'port', 'pump',
        # Wound care
        'bandage', 'gauze', 'dressing', 'sponge', 'pad', 'compress', 'swab',
        'hydrofibre', 'hydrogel', 'foam', 'alginate', 'collagen',
        # PPE
        'glove', 'gloves', 'mask', 'gown', 'drape', 'shield', 'goggles',
        'cap', 'shoe', 'cover', 'apron',
        # Containers
        'bottle', 'bag', 'vial', 'ampoule', 'ampule', 'jar', 'container',
        'box', 'kit', 'tray', 'pack', 'packet', 'pouch', 'sachet',
        # Medications forms
        'tablet', 'capsule', 'pill', 'lozenge', 'suppository', 'patch',
        'cream', 'ointment', 'gel', 'lotion', 'spray', 'drops', 'inhaler',
        # Other medical items
        'wire', 'mesh', 'implant', 'prosthesis', 'clip', 'staple',
        'film', 'sheet', 'strip', 'roll', 'ball', 'plug', 'seal',
        # Food/consumables
        'bar', 'powder', 'granule', 'piece', 'unit', 'item', 'product',
        'stick', 'cube', 'wafer', 'disc', 'disk', 'pellet'
    })
    
    # Brand names to recognize
    COMMON_BRANDS: Set[str] = field(default_factory=lambda: {
        'vicryl', 'prolene', 'ethilon', 'monocryl', 'pds', 'chromic',
        'viaflex', 'baxter', '3m', 'johnson', 'bd', 'braun', 'abbott',
        'medtronic', 'stryker', 'smith', 'nephew', 'covidien', 'ethicon',
        'hershey', 'nestle', 'kraft', 'cadbury', 'mars', 'ferrero',
        'kimberly', 'clark', 'cardinal', 'mckesson', 'owens', 'minor'
    })
    
    # Descriptive terms (for Position 2)
    DESCRIPTIVE_TERMS: Set[str] = field(default_factory=lambda: {
        'surgical', 'medical', 'sterile', 'disposable', 'reusable',
        'elastic', 'adhesive', 'cohesive', 'transparent', 'opaque',
        'absorbable', 'non-absorbable', 'braided', 'monofilament',
        'chocolate', 'vanilla', 'strawberry', 'mint', 'caramel',
        'adult', 'pediatric', 'infant', 'neonatal',
        'heavy', 'light', 'medium', 'standard', 'extra', 'ultra',
        'regular', 'large', 'small', 'mini', 'micro', 'macro'
    })
    
    # Seasonal/thematic descriptors (lower priority)
    SEASONAL_TERMS: Set[str] = field(default_factory=lambda: {
        'halloween', 'christmas', 'easter', 'valentine', 'thanksgiving',
        'holiday', 'seasonal', 'limited', 'special', 'edition'
    })
    
    # Packaging and material descriptors (for Position 5)
    PACKAGING_MATERIALS: Set[str] = field(default_factory=lambda: {
        'plastic', 'glass', 'metal', 'paper', 'foil', 'cardboard',
        'polyethylene', 'polypropylene', 'pvc', 'pet', 'hdpe', 'ldpe',
        'amber', 'clear', 'opaque', 'translucent',
        'rectangular', 'round', 'square', 'oval',
        'wide-mouth', 'narrow-mouth', 'flip-top', 'screw-cap',
        'peel', 'blister', 'bulk', 'individual', 'wrapped'
    })
    
    # Metric units (preferred)
    METRIC_UNITS: Dict[str, str] = field(default_factory=lambda: {
        'millimeter': 'mm', 'millimeters': 'mm', 'millimetre': 'mm', 'millimetres': 'mm', 'mm': 'mm',
        'centimeter': 'cm', 'centimeters': 'cm', 'centimetre': 'cm', 'centimetres': 'cm', 'cm': 'cm',
        'meter': 'm', 'meters': 'm', 'metre': 'm', 'metres': 'm', 'm': 'm',
        'milliliter': 'ml', 'milliliters': 'ml', 'millilitre': 'ml', 'millilitres': 'ml', 'ml': 'ml',
        'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l', 'l': 'l',
        'milligram': 'mg', 'milligrams': 'mg', 'mg': 'mg',
        'gram': 'g', 'grams': 'g', 'g': 'g',
        'kilogram': 'kg', 'kilograms': 'kg', 'kg': 'kg',
        'celsius': 'C', 'c': 'C', 'centigrade': 'C',
        'degree': 'DEG', 'degrees': 'DEG', 'deg': 'DEG',
    })
    
    # Imperial units
    IMPERIAL_UNITS: Dict[str, str] = field(default_factory=lambda: {
        'inch': 'IN', 'inches': 'IN', 'in': 'IN', '"': 'IN',
        'foot': 'FT', 'feet': 'FT', 'ft': 'FT', "'": 'FT',
        'yard': 'YD', 'yards': 'YD', 'yd': 'YD',
        'ounce': 'OZ', 'ounces': 'OZ', 'oz': 'OZ',
        'pound': 'LB', 'pounds': 'LB', 'lb': 'LB', 'lbs': 'LB',
        'fahrenheit': 'F', 'f': 'F',
        'french': 'FR', 'fr': 'FR', 'gauge': 'G', 'ga': 'G',
    })
    
    # Side indicators
    SIDE_INDICATORS: Dict[str, str] = field(default_factory=lambda: {
        'left': 'LT', 'right': 'RT', 'lt': 'LT', 'rt': 'RT', 
        'rl': 'RL', 'bilateral': 'BL', 'unilateral': 'UL'
    })


class StrictTokenizer:
    """Tokenizer with strict duplicate prevention"""
    
    def __init__(self, rules: ShortNameRules):
        self.rules = rules
        self.used_indices = set()  # Track which word indices have been used
    
    def tokenize(self, text: str) -> List[TokenInfo]:
        """Tokenize text with position tracking"""
        tokens = []
        words = text.split()
        
        for i, word in enumerate(words):
            word_lower = word.lower()
            
            # Skip if already used
            if i in self.used_indices:
                continue
            
            # Check for size patterns (number + unit)
            size_match = re.match(r'^(\d+\.?\d*)\s*([a-zA-Z]+)$', word)
            if size_match:
                number, unit = size_match.groups()
                unit_lower = unit.lower()
                
                if unit_lower in self.rules.METRIC_UNITS or unit_lower in self.rules.IMPERIAL_UNITS:
                    tokens.append(TokenInfo(
                        value=f"{number}{unit}",
                        original=word,
                        token_type='size',
                        priority=90,
                        position_hints=[Position.PRIMARY_VARIANT, Position.SECONDARY_VARIANT],
                        index=i
                    ))
                    continue
            
            # Check for percentage
            if '%' in word:
                tokens.append(TokenInfo(
                    value=word,
                    original=word,
                    token_type='percentage',
                    priority=85,
                    position_hints=[Position.PRODUCT_NAME],
                    index=i
                ))
                continue
            
            # Check for product codes
            if re.match(r'^[A-Z]\d{2,4}[A-Z]?$', word.upper()):
                tokens.append(TokenInfo(
                    value=word.upper(),
                    original=word,
                    token_type='product_code',
                    priority=70,
                    position_hints=[Position.PRIMARY_VARIANT, Position.SECONDARY_VARIANT],
                    index=i
                ))
                continue
            
            # Check for product types (HIGHEST PRIORITY)
            if word_lower in self.rules.PRODUCT_TYPES:
                tokens.append(TokenInfo(
                    value=word,
                    original=word,
                    token_type='product_type',
                    priority=100,  # Highest priority
                    position_hints=[Position.PRODUCT_TYPE],
                    index=i
                ))
                continue
            
            # Check for brand names
            if word_lower in self.rules.COMMON_BRANDS:
                tokens.append(TokenInfo(
                    value=word.upper(),
                    original=word,
                    token_type='brand',
                    priority=80,
                    position_hints=[Position.PRIMARY_VARIANT],
                    index=i
                ))
                continue
            
            # Check for descriptive terms
            if word_lower in self.rules.DESCRIPTIVE_TERMS:
                tokens.append(TokenInfo(
                    value=word,
                    original=word,
                    token_type='descriptor',
                    priority=75,
                    position_hints=[Position.PRODUCT_NAME, Position.SECONDARY_VARIANT],
                    index=i
                ))
                continue
            
            # Check for seasonal terms (lower priority)
            if word_lower in self.rules.SEASONAL_TERMS:
                tokens.append(TokenInfo(
                    value=word,
                    original=word,
                    token_type='seasonal',
                    priority=50,  # Lower priority
                    position_hints=[Position.SECONDARY_VARIANT, Position.ADDITIONAL_DESCRIPTOR],
                    index=i
                ))
                continue
            
            # Check for packaging materials
            if word_lower in self.rules.PACKAGING_MATERIALS:
                tokens.append(TokenInfo(
                    value=word,
                    original=word,
                    token_type='packaging',
                    priority=60,
                    position_hints=[Position.ADDITIONAL_DESCRIPTOR],
                    index=i
                ))
                continue
            
            # Check for side indicators
            if word_lower in self.rules.SIDE_INDICATORS:
                tokens.append(TokenInfo(
                    value=self.rules.SIDE_INDICATORS[word_lower],
                    original=word,
                    token_type='side',
                    priority=70,
                    position_hints=[Position.PRIMARY_VARIANT],
                    index=i
                ))
                continue
            
            # Skip common words
            if word_lower in ['with', 'and', 'or', 'for', 'of', 'the', 'a', 'an', 'x']:
                continue
            
            # Default: unclassified token
            tokens.append(TokenInfo(
                value=word,
                original=word,
                token_type='unclassified',
                priority=40,
                position_hints=[Position.PRODUCT_NAME, Position.SECONDARY_VARIANT],
                index=i
            ))
        
        # Sort by priority (highest first)
        tokens.sort(key=lambda x: (-x.priority, x.index))
        
        return tokens
    
    def mark_token_used(self, token: TokenInfo):
        """Mark a token as used by its index"""
        token.is_used = True
        self.used_indices.add(token.index)


class ShortNameValidator:
    """Validates short names according to the rules"""
    
    def __init__(self, rules: ShortNameRules):
        self.rules = rules
    
    def validate_length(self, short_name: str) -> Tuple[bool, Optional[str]]:
        """Validate the total length of the short name"""
        if len(short_name) > self.rules.MAX_LENGTH:
            return False, f"Short name exceeds {self.rules.MAX_LENGTH} characters (current: {len(short_name)})"
        return True, None
    
    def validate_allowed_characters(self, short_name: str) -> Tuple[bool, Optional[str]]:
        """Check if only allowed characters are used"""
        if not re.match(self.rules.ALLOWED_CHARS_PATTERN, short_name):
            prohibited_found = []
            for char in short_name:
                if char in self.rules.PROHIBITED_CHARS:
                    prohibited_found.append(char)
            
            if prohibited_found:
                return False, f"Prohibited characters found: {', '.join(set(prohibited_found))}"
            else:
                return False, "Contains characters outside allowed set"
        return True, None
    
    def validate_prohibited_patterns(self, short_name: str) -> Tuple[bool, Optional[str]]:
        """Check for prohibited character patterns"""
        for pattern, description in self.rules.PROHIBITED_PATTERNS:
            if re.search(pattern, short_name):
                return False, f"Prohibited pattern: {description}"
        return True, None
    
    def validate_singular_form(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if text uses singular form"""
        words = text.lower().split()
        plural_exceptions = {
            'glass', 'wireless', 'stainless', 'seamless', 'plus', 'lens',
            'bypass', 'duchess', 'princess', 'countess', 'congress',
            'gloves', 'scissors', 'forceps'  # Medical exceptions
        }
        
        for word in words:
            if word.upper() in ['OPS', 'IVS', 'ABS', 'EMS', 'NS'] or word in plural_exceptions:
                continue
            
            # Check for 's' ending (but not 'ss')
            if word.endswith('s') and not word.endswith('ss'):
                if word not in ['diabetes', 'rabies', 'herpes', 'lens']:
                    return False, f"Possible plural form detected: {word}"
        
        return True, None
    
    def validate_no_duplicate_meaning(self, components: List[ShortNameComponent]) -> Tuple[bool, Optional[str]]:
        """Ensure no duplicate meanings in the description"""
        # Check for duplicate values
        value_counts = {}
        for comp in components:
            val_lower = comp.value.lower()
            if val_lower in value_counts:
                value_counts[val_lower].append(comp.position.value)
            else:
                value_counts[val_lower] = [comp.position.value]
        
        # Find duplicates
        duplicates = []
        for value, positions in value_counts.items():
            if len(positions) > 1:
                duplicates.append(f"'{value}' in positions {positions}")
        
        if duplicates:
            return False, f"Duplicate values found: {'; '.join(duplicates)}"
        
        return True, None


class AbbreviationDictionary:
    """Manages abbreviation dictionary from external sources"""
    
    def __init__(self):
        self.abbreviations: Dict[str, str] = {}
        self.loaded_from: Optional[str] = None
    
    def load_from_file(self, filepath: str) -> bool:
        """Load abbreviations from Excel or CSV file"""
        try:
            path = Path(filepath)
            
            if not path.exists():
                print(f"Error: File not found: {filepath}")
                return False
            
            # Load based on file extension
            if path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(filepath, engine='openpyxl')
            elif path.suffix.lower() == '.csv':
                df = pd.read_csv(filepath)
            else:
                print(f"Error: Unsupported file format: {path.suffix}")
                return False
            
            # Assume first column is full form, second is abbreviation
            if len(df.columns) < 2:
                print("Error: Dictionary file must have at least 2 columns")
                return False
            
            # Build dictionary
            count = 0
            for _, row in df.iterrows():
                full_form = str(row.iloc[0]).strip()
                abbreviation = str(row.iloc[1]).strip()
                
                if full_form and abbreviation and full_form != 'nan':
                    # Store in lowercase for case-insensitive matching
                    self.abbreviations[full_form.lower()] = abbreviation.upper()
                    count += 1
            
            self.loaded_from = filepath
            print(f"Successfully loaded {count} unique abbreviations from {filepath}")
            return True
            
        except Exception as e:
            print(f"Error loading dictionary: {str(e)}")
            return False
    
    def get_abbreviation(self, term: str) -> Optional[str]:
        """Get abbreviation for a term"""
        return self.abbreviations.get(term.lower())


class CorrectedShortNameProcessor:
    """Processor with corrected duplicate prevention and dictionary usage"""
    
    def __init__(self, dictionary_path: Optional[str] = None):
        self.rules = ShortNameRules()
        self.validator = ShortNameValidator(self.rules)
        self.dictionary = AbbreviationDictionary()
        
        if dictionary_path:
            self.dictionary.load_from_file(dictionary_path)
    
    def process_full_description(self, full_description: str) -> Dict[str, any]:
        """Process a full description with strict duplicate prevention"""
        result = {
            'original': full_description,
            'short_name': '',
            'components': [],
            'tokens': [],
            'messages': [],
            'success': False,
            'character_count': 0
        }
        
        try:
            # Create new tokenizer for each processing
            tokenizer = StrictTokenizer(self.rules)
            
            # Step 1: Tokenize
            tokens = tokenizer.tokenize(full_description)
            result['tokens'] = [self._token_to_dict(t) for t in tokens]
            
            # Step 2: Build components with strict no-duplicate logic
            components = self._build_components_strict(tokens, tokenizer)
            
            # Step 3: Build and validate short name
            short_name, messages = self._build_and_validate(components)
            
            result['short_name'] = short_name
            result['components'] = [self._component_to_dict(c) for c in components]
            result['messages'] = messages
            result['character_count'] = len(short_name)
            result['success'] = all('Error' not in msg for msg in messages)
            
        except Exception as e:
            result['messages'].append(f"Processing Error: {str(e)}")
            result['success'] = False
        
        return result
    
    def _build_components_strict(self, tokens: List[TokenInfo], tokenizer: StrictTokenizer) -> List[ShortNameComponent]:
        """Build components with strict duplicate prevention"""
        components = []
        filled_positions = set()
        
        # CRITICAL: First find and lock the product type
        product_type_component = None
        for token in tokens:
            if token.token_type == 'product_type' and not token.is_used:
                # Position 1 MUST NOT be abbreviated - use full spelling
                value = token.value.capitalize()  # Capitalize, not uppercase
                
                product_type_component = ShortNameComponent(
                    position=Position.PRODUCT_TYPE,
                    value=value,  # Full spelling, no abbreviation
                    original_value=token.original,
                    is_mandatory=True,
                    applied_rules=['product_type', 'no_abbreviation', 'full_spelling'],
                    token_index=token.index
                )
                
                # Mark this token as used immediately
                tokenizer.mark_token_used(token)
                break
        
        # If we found a product type, add it first
        if product_type_component:
            components.append(product_type_component)
            filled_positions.add(Position.PRODUCT_TYPE)
        else:
            # Try to infer product type from the last noun-like word
            for token in reversed(tokens):
                if not token.is_used and token.token_type in ['unclassified']:
                    # Check if it could be a product type
                    if any(token.value.lower().endswith(suffix) for suffix in ['bar', 'piece', 'unit']):
                        value = token.value.capitalize()
                        
                        product_type_component = ShortNameComponent(
                            position=Position.PRODUCT_TYPE,
                            value=value,
                            original_value=token.original,
                            is_mandatory=True,
                            applied_rules=['inferred_type', 'no_abbreviation'],
                            token_index=token.index
                        )
                        
                        components.append(product_type_component)
                        filled_positions.add(Position.PRODUCT_TYPE)
                        tokenizer.mark_token_used(token)
                        break
        
        # Now fill other positions
        position_rules = [
            (Position.PRIMARY_VARIANT, ['size', 'brand', 'side', 'product_code']),
            (Position.PRODUCT_NAME, ['percentage', 'descriptor']),
            (Position.SECONDARY_VARIANT, ['descriptor', 'seasonal', 'unclassified']),
            (Position.ADDITIONAL_DESCRIPTOR, ['packaging', 'seasonal'])
        ]
        
        for position, preferred_types in position_rules:
            if position in filled_positions:
                continue
            
            # Try each preferred type
            for pref_type in preferred_types:
                component_added = False
                
                for token in tokens:
                    if (token.token_type == pref_type and 
                        not token.is_used and 
                        position in token.position_hints):
                        
                        # Format the value
                        value = self._format_token_value(token, position)
                        
                        # Apply dictionary abbreviation if:
                        # 1. Not Position 1 (Product Type)
                        # 2. Dictionary has an abbreviation
                        if position != Position.PRODUCT_TYPE:
                            abbrev = self.dictionary.get_abbreviation(token.original)
                            if abbrev:
                                value = abbrev
                                applied_rules = [token.token_type, 'dictionary_abbrev']
                            else:
                                applied_rules = [token.token_type, 'no_abbrev_found']
                        else:
                            applied_rules = [token.token_type, 'no_abbreviation']
                        
                        component = ShortNameComponent(
                            position=position,
                            value=value,
                            original_value=token.original,
                            is_mandatory=False,
                            applied_rules=applied_rules,
                            token_index=token.index
                        )
                        
                        components.append(component)
                        filled_positions.add(position)
                        tokenizer.mark_token_used(token)
                        component_added = True
                        break
                
                if component_added:
                    break
        
        # Sort by position
        components.sort(key=lambda x: x.position.value)
        
        return components
    
    def _format_token_value(self, token: TokenInfo, position: Position) -> str:
        """Format token value based on type and position"""
        value = token.value
        
        if token.token_type == 'size':
            # Format size with units
            match = re.match(r'^(\d+\.?\d*)\s*([a-zA-Z]+)$', value)
            if match:
                number, unit = match.groups()
                unit_lower = unit.lower()
                
                # Convert to standard abbreviation
                if unit_lower in self.rules.METRIC_UNITS:
                    unit = self.rules.METRIC_UNITS[unit_lower]
                elif unit_lower in self.rules.IMPERIAL_UNITS:
                    unit = self.rules.IMPERIAL_UNITS[unit_lower]
                
                value = f"{number}{unit}"
        
        elif token.token_type == 'percentage':
            # Remove spaces before %
            value = re.sub(r'\s*%', '%', value)
        
        elif token.token_type == 'brand':
            # Brands are uppercase
            value = value.upper()
        
        elif token.token_type == 'seasonal':
            # Seasonal terms - check dictionary first
            value = value.capitalize()
        
        elif token.token_type in ['descriptor', 'packaging']:
            # Use proper case
            value = value.capitalize()
        
        elif token.token_type == 'product_type' and position == Position.PRODUCT_TYPE:
            # Product type in Position 1 - NEVER abbreviate
            value = value.capitalize()
        
        else:
            # Default
            value = value.upper()
        
        return value
    
    def _build_and_validate(self, components: List[ShortNameComponent]) -> Tuple[str, List[str]]:
        """Build and validate the short name"""
        messages = []
        
        # Check mandatory positions
        positions = {c.position for c in components}
        for mandatory in self.rules.MANDATORY_POSITIONS:
            if mandatory not in positions:
                messages.append(f"Warning: Mandatory position {mandatory.name} is missing")
        
        # Build short name
        values = [c.value for c in components]
        short_name = ' '.join(values)
        
        # Clean up
        short_name = re.sub(r'\s+', ' ', short_name.strip())
        
        # Validate
        validations = [
            self.validator.validate_length(short_name),
            self.validator.validate_allowed_characters(short_name),
            self.validator.validate_prohibited_patterns(short_name),
            self.validator.validate_singular_form(short_name),
            self.validator.validate_no_duplicate_meaning(components)
        ]
        
        for is_valid, message in validations:
            if not is_valid and message:
                messages.append(f"Validation Error: {message}")
        
        if not any('Error' in msg for msg in messages):
            messages.append(f"Success: Generated short name with {len(short_name)} characters")
        
        return short_name, messages
    
    def _token_to_dict(self, token: TokenInfo) -> Dict:
        """Convert token to dictionary"""
        return {
            'value': token.value,
            'original': token.original,
            'type': token.token_type,
            'priority': token.priority,
            'position_hints': [p.name for p in token.position_hints],
            'index': token.index,
            'used': token.is_used
        }
    
    def _component_to_dict(self, component: ShortNameComponent) -> Dict:
        """Convert component to dictionary"""
        return {
            'position': component.position.name,
            'position_number': component.position.value,
            'value': component.value,
            'original': component.original_value,
            'mandatory': component.is_mandatory,
            'rules_applied': component.applied_rules,
            'token_index': component.token_index
        }


# Convenience functions

def print_result(result: Dict[str, any], detailed: bool = True):
    """Pretty print the processing result"""
    print(f"\n{'='*60}")
    print(f" RESULT")
    print(f"{'='*60}")
    print(f" Input:      {result['original']}")
    print(f" Output:     {result['short_name']}")
    print(f" Length:     {result['character_count']}/35 characters")
    print(f"  Status:     {'SUCCESS' if result['success'] else 'FAILED'}")
    
    if detailed and result['components']:
        print("\n Components breakdown:")
        for comp in result['components']:
            mandatory = "red error" if comp['mandatory'] else "while error"
            print(f"   {mandatory} Position {comp['position_number']}: {comp['value']:20} ← {comp['original']}")
            if comp['rules_applied']:
                print(f"      Rules: {', '.join(comp['rules_applied'])}")
    
    if result['messages']:
        print("\n Messages:")
        for msg in result['messages']:
            if 'Error' in msg:
                print(f" {msg}")
            elif 'Warning' in msg:
                print(f" {msg}")
            else:
                print(f" {msg}")
    
    print(f"{'='*60}\n")