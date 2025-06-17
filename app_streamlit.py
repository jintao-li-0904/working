"""
Item description Short Name Generator - Streamlit App
Easy to use version
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import os



def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# add current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# load core processor（save original code file as processor.py）
try:
    from processor import CorrectedShortNameProcessor, print_result
except ImportError:
    st.error("Make sure processor.py file is in the same directory as this app.")
    st.stop()

# Set the page configuration
st.set_page_config(
    page_title="Item Description Short Name Generator",
    page_icon="",
    layout="wide"
)

# Initialize session state
if 'processor' not in st.session_state:
    st.session_state.processor = None
if 'history' not in st.session_state:
    st.session_state.history = []

# Title and description
st.title("Item Description Short Name Generator")
st.markdown("""
### Funtion Description
- Convert the long product description into a short description
- Strictly follow the GS1 Short Name Guidelines
- Limitation: 35 characters
- Supports custom dictionary for abbreviations
""")

# Side Bar - Dictionary Settings
with st.sidebar:
    st.header("Dictionary Settings")
    
    # Upload dictionary file
    uploaded_file = st.file_uploader(
        "Upload Dictionary File",
        type=['xlsx', 'xls', 'csv'],
        help="Excel or CSV file, with first column Fullterm and second Abbreviation"
    )
    
    if uploaded_file is not None:
        # Save the uploaded file temporarily
        save_path = f"temp_{uploaded_file.name}"
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # load the dictionary 
        try:
            st.session_state.processor = CorrectedShortNameProcessor(save_path)
            st.success(f"Successfuly load the external dictionary! There are {len(st.session_state.processor.dictionary.abbreviations)} abbreviations in the dictionary.")
            
            # Display partial dictionary examples
            with st.expander("View dictionary examples"):
                dict_items = list(st.session_state.processor.dictionary.abbreviations.items())[:10]
                df_dict = pd.DataFrame(dict_items, columns=['Fullterm', 'Abbreviation'])
                st.dataframe(df_dict)
        except Exception as e:
            st.error(f"Fail to load the dictionary: {str(e)}")
    else:
        # try to find the detault dictionary file
        possible_paths = [
            # resource_path("dictionary.xlsx"),  # Directory after packaging
            # resource_path("merged_dictionary.xlsx"),
            # Path("dictionary.xlsx"),  # Same Directory
            Path("merged_dictionary.xlsx"),  # Backup name for the dictionary 
            # Path(__file__).parent / "dictionary.xlsx",  # same directory
            # Path(__file__).parent / "data" / "dictionary.xlsx",  # data saved directory
        ]
        
        default_dict_path = None
        for path in possible_paths:
            if path.exists():
                default_dict_path = str(path)
                break
        
        if default_dict_path:
            if st.button(f"Use the default dictionary ({Path(default_dict_path).name})"):
                try:
                    st.session_state.processor = CorrectedShortNameProcessor(default_dict_path)
                    st.success(f"Successfully load the default dictionary! There are{len(st.session_state.processor.dictionary.abbreviations)}Abbreviations in the dictionary.")
                except Exception as e:
                    st.error(f"Fail to load the default dictionary: {str(e)}")
        else:
            st.info("Please upload dictionary file (Use Excel or CSV file format)")
            st.info("Hint: Name the dictionary as 'merged_dictionary' and save to the same directory as default dictionary.")
    
    st.divider()
    
    # Rules and Naming Guidelines
    st.header("Naming Guidelines")
    st.markdown("""
    **Five-Position Strcuture:**
    1. **Product Type (noun)** (Mandatory, No abbreviation)
    2. **Product name (adjective/descriptor)** (Optional)
    3. **Primary variant/descriptor** (Optional)
    4. **Secondary variant/descriptor** (Optional)
    5. **Additional descriptor** (Optional)
    
    **Key rules:**
    - Maximum 35 characters limit(including spaces)
    - Use abbreviations from the dictionary
    - Singular nouns only
    - No spaces between number and unit of measure (e.g., "500milliliters")
    """)

# Main content area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("Input")
    
    # Input full product description
    full_description = st.text_area(
        "Input Full Product Description",
        height=100,
        placeholder="Example: Solution Dextrose 5% 500 milliliters Bottle Viaflex Non-Latex",
        help="Input full product description in English. The description should be clear and concise, following the GS1 Short Name Guidelines."
    )
    
    # Process and clear buttons
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        process_btn = st.button("Generate short description", type="primary", use_container_width=True)
    with col_btn2:
        clear_btn = st.button("Delete", use_container_width=True)
    
    # Input examples
    st.subheader("Input examples")
    examples = [
        "Solution Dextrose 5% 500 milliliters Bottle Viaflex Non-Latex",
        "Halloween HERSHEY chocolate bar 500 kilograms",
        "Suture VICRYL 0 Taper CT1 J340H",
        "Tape Surgical 1.25cm x 9.14m",
        "Scissor Mayo 170mm Straight"
    ]
    
    for i, example in enumerate(examples):
        if st.button(f"Examples {i+1}: {example[:40]}...", key=f"example_{i}"):
            st.session_state.example_text = example
            st.rerun()
    
    # If an example is selected, use it as input
    if 'example_text' in st.session_state:
        full_description = st.session_state.example_text
        del st.session_state.example_text

with col2:
    st.header("Output")
    
    # Process the input
    if process_btn and full_description:
        if st.session_state.processor is None:
            st.error("Please load the dictionary first!")
        else:
            with st.spinner("Processing..."):
                result = st.session_state.processor.process_full_description(full_description)
                
                # Add to history
                st.session_state.history.append({
                    'input': full_description,
                    'output': result['short_name'],
                    'success': result['success']
                })
                
                # Display result
                if result['success']:
                    st.success(f"**Successfully generated**")
                    st.markdown(f"### Short Description: `{result['short_name']}`")
                    st.markdown(f"**Number of Charactors** {result['character_count']}/35")
                else:
                    st.error("**Fail to generate**")
                    st.markdown(f"### Short Description`{result['short_name']}`")
                
                # Detailed breakdown
                with st.expander("Detailed breakdown", expanded=True):
                    if result['components']:
                        df_components = pd.DataFrame([
                            {
                                'Position': comp['position_number'],
                                'Name of Position': comp['position'],
                                'Value': comp['value'],
                                'Original Value': comp['original'],
                                'Mandatory': 'Yes' if comp['mandatory'] else 'No',
                                'Applied rules': ', '.join(comp['rules_applied'])
                            }
                            for comp in result['components']
                        ])
                        st.dataframe(df_components, use_container_width=True)
                
                # Messages
                if result['messages']:
                    with st.expander("Process Messages"):
                        for msg in result['messages']:
                            if 'Error' in msg:
                                st.error(msg)
                            elif 'Warning' in msg:
                                st.warning(msg)
                            else:
                                st.info(msg)
    
    # Delete input button
    if clear_btn:
        st.rerun()

# Process History
st.divider()
st.header("Process History")

if st.session_state.history:
    # create a DataFrame from history
    df_history = pd.DataFrame(st.session_state.history)
    df_history['Situation'] = df_history['success'].map({True: 'Successful', False: 'Failed'})
    df_history = df_history[['input', 'output', 'Situation']].rename(columns={
        'input': 'Input',
        'output': 'Output'
    })
    
    st.dataframe(df_history, use_container_width=True)
    
    # delete history button
    if st.button("Delete History"):
        st.session_state.history = []
        st.rerun()
else:
    st.info("No history available yet")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: gray;'>
    <p>Item Description Short name generator v1.0</p>
    <p>All rules are based on GS1 documentaiton</p>
</div>
""", unsafe_allow_html=True)
