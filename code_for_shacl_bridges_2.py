import pandas as pd
from copy import deepcopy
import networkx as nx
import re
from pyshacl import Validator
from rdflib import Graph
from rdflib.compare import to_isomorphic, graph_diff

# Function to find the longest path in shape bridge
def find_longest_path(graph):
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("The graph is not a Directed Acyclic Graph (DAG).")

    # Find the longest path using NetworkX's built-in function
    longest_path = nx.dag_longest_path(graph)
    return longest_path


# Function to find the longest path in shape validation
def find_longest_path_1(graph):
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("The graph is not a Directed Acyclic Graph (DAG).")

    # Find the longest path using NetworkX's built-in function
    longest_path_1 = nx.dag_longest_path(graph)
    return longest_path_1


# Preprocess the data: Interpret "-" correctly by duplicating the previous row's "From" and "To"
def preprocess_graph_data(graph_data):
    processed_data = []
    last_from, last_to = None, None
    for row in graph_data:
        from_node, to_node, relation, target_node = row

        if from_node == "-":
            from_node = last_from
        if to_node == "-":
            to_node = last_to
        if relation == "-":
            relation = ""  # Empty relation means no relation
        if target_node == "-":
            target_node = ""  # Empty target means no target node

        # Update last known 'from' and 'to' nodes
        last_from, last_to = from_node, to_node

        processed_data.append((from_node, to_node, relation, target_node))

    return processed_data


# Function to extract common entries between two dataframes based on a column label
def get_common_entries(df, reference_df, reference_col):
    return df[df['label'].isin(reference_df[reference_col])]


# Function to concatenate and deduplicate multiple dataframes
def concat_and_deduplicate(dfs_list):
    return pd.concat(dfs_list).drop_duplicates()


# Function to find entries specific to one dataframe compared to another
def find_specific_entries(df, common_df):
    return df[~df['label'].isin(common_df['label'])]


# Process common entries for shape_bridge_df
def process_shape_bridge(classes_df, shape_bridge_df):
    common_from = get_common_entries(classes_df, shape_bridge_df, 'From')
    common_to = get_common_entries(classes_df, shape_bridge_df, 'To')
    common_relation = get_common_entries(classes_df, shape_bridge_df, 'Relation')
    common_target = get_common_entries(classes_df, shape_bridge_df, 'Target')

    return concat_and_deduplicate([common_from, common_to, common_relation, common_target])


# Process common entries for shape_validation_df
def process_shape_validation(classes_df, shape_validation_df):
    common_subject = get_common_entries(classes_df, shape_validation_df, 'subject_label')
    common_predicate = get_common_entries(classes_df, shape_validation_df, 'predicate_label')
    common_object = get_common_entries(classes_df, shape_validation_df, 'object_label')

    return concat_and_deduplicate([common_subject, common_predicate, common_object])


# Main function to process and compare entries between shape_bridge_df and shape_validation_df
def process_and_compare_entries(classes_df, shape_bridge_df, shape_validation_df):
    # Process shape_bridge_df and shape_validation_df common entries
    common_entries_sb = process_shape_bridge(classes_df, shape_bridge_df)
    common_entries_sv = process_shape_validation(classes_df, shape_validation_df)

    # Find the intersection of common entries
    common_entries = common_entries_sv[common_entries_sv['label'].isin(common_entries_sb['label'])]

    # Find unique entries specific to SV and SB
    sv_specific = find_specific_entries(common_entries_sv, common_entries)
    sb_specific = find_specific_entries(common_entries_sb, common_entries)

    return common_entries, sv_specific, sb_specific


# Function to generate SHACL shape properties with proper nesting
def generate_nested_shacl(G, node, visited=set()):
    """
    Recursively generates SHACL shapes with nested properties
    """
    if node in visited:
        return ""

    visited.add(node)

    shacl_shapes = ""

    for neighbor in G.successors(node):
        predicate = G[node][neighbor]['predicate']

        # Nested validation for the target class (neighbor)
        shacl_shapes += f"""
    # Validation for {node} - {predicate} - {neighbor}
    sh:property [
        sh:path :{predicate} ;
        sh:node [
            a sh:NodeShape ;
            sh:class :{neighbor} ;
"""

        # Recursively build nested SHACL for neighbor nodes
        nested_shapes = generate_nested_shacl(G, neighbor, visited)

        if nested_shapes:
            shacl_shapes += f"""
            # Nested validation for {neighbor}
{nested_shapes}
"""

        shacl_shapes += f"""
        ] ;
        sh:message "{node} must have a {predicate} property pointing to a {neighbor}." ;
    ] ;
"""

    return shacl_shapes


# Function to create an undirected graph with weighted edges
def create_weighted_graph(df):
    G = nx.Graph()
    for _, row in df.iterrows():
        # Add both directions with different weights
        G.add_edge(row['subject_label'], row['object_label'], weight=1)
        G.add_edge(row['object_label'], row['subject_label'], weight=2)
    return G


# Function to compute closeness centrality with weights
def compute_closeness_centrality(G):
    return nx.closeness_centrality(G, distance='weight')


# Function to create a directed graph
def create_directed_graph(df):
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_edge(row['subject_label'], row['object_label'])
    return G


# Function to find the node with the highest centrality and resolve ties
def find_highest_centrality_node(closeness_centrality, directed_graph):
    max_centrality_value = max(closeness_centrality.values())
    candidates = [node for node, centrality in closeness_centrality.items() if centrality == max_centrality_value]

    if len(candidates) > 1:
        # If there's a tie, resolve by selecting the node with the highest out-degree
        candidate_out_degrees = {node: directed_graph.out_degree(node) for node in candidates}
        return max(candidate_out_degrees, key=candidate_out_degrees.get)
    else:
        # Only one node has the highest centrality
        return candidates[0]


# Function to output the highest centrality node and its value
def output_highest_centrality_node(closeness_centrality, highest_centrality_node):
    highest_centrality_value = closeness_centrality[highest_centrality_node]
    print(f"Node with the highest closeness centrality: {highest_centrality_node}")
    print(f"Closeness centrality value: {highest_centrality_value}")


# Main function to process the data and compute the highest centrality node
def process_graph_centrality(df):
    # Create the undirected graph with weighted edges
    G_1 = create_weighted_graph(df)

    # Compute closeness centrality
    closeness_centrality = compute_closeness_centrality(G_1)

    # Create a directed graph for outgoing edges
    G_2 = create_directed_graph(df)

    # Find the node with the highest centrality
    highest_centrality_node = find_highest_centrality_node(closeness_centrality, G_2)

    # Output the node with the highest centrality and its value
    output_highest_centrality_node(closeness_centrality, highest_centrality_node)



def generate_variable_names(entities):
    """
    Generate variable names for unique entities, mapping each entity to a unique variable.
    Example: {'Process': '?variable_x', 'Experiment': '?variable_y', ...}
    """
    variable_mapping = {}
    alphabet = 'abcdefghijklmnopqrstuvwxyz'
    var_counter = 0  # start from 0

    for entity in entities:
        if entity not in variable_mapping:
            # Generate variable names like ?variable_x, ?variable_y, ?variable_z, etc.
            if var_counter < len(alphabet):
                variable_mapping[entity] = f"?variable_{alphabet[var_counter]}"
            else:
                # Handle cases where the alphabet cycles, e.g., ?variable_aa, ?variable_ab, etc.
                first_letter = alphabet[(var_counter // len(alphabet)) - 1]
                second_letter = alphabet[var_counter % len(alphabet)]
                variable_mapping[entity] = f"?variable_{first_letter}{second_letter}"
            var_counter += 1

    return variable_mapping



def sparql_query_text_from_dataframes(df_main, df_relationships):
    # Forward fill '-' values in 'From' and 'To' columns in the main DataFrame to copy previous row's value
    df_main['From'] = df_main['From'].replace('-', pd.NA).ffill()
    df_main['To'] = df_main['To'].replace('-', pd.NA).ffill()

    # Collect all unique entities from 'From', 'To', and 'Target' columns in the main DataFrame
    unique_entities = pd.concat([df_main['From'], df_main['To'], df_main['Target'],
                                 df_relationships['subject_label'], df_relationships['object_label']]).dropna().unique()

    # Generate dynamic variable names for unique entities
    variable_mapping = generate_variable_names(unique_entities)

    # Lists to store the CONSTRUCT and WHERE statements
    construct_statements = []
    where_statements = []
    extra_conditions = []

    # Generate the WHERE statements (mapping the "From" entities to variables)
    for _, row in df_main.iterrows():
        from_value = row['From']
        to_value = row['To']
        relation_value = row['Relation']
        target_value = row['Target']

        from_var = variable_mapping[from_value]  # Variable for 'From'
        to_var = variable_mapping[to_value]      # Variable for 'To' (reused as 'Target' later)

        # WHERE clause: original mappings
        where_statements.append(f"{from_var} rdf:type ex:{from_value}.")

    # Generate the CONSTRUCT statements (translate "From" to "To" and handle relations)
    for _, row in df_main.iterrows():
        from_value = row['From']
        to_value = row['To']
        relation_value = row['Relation']
        target_value = row['Target']

        from_var = variable_mapping[from_value]  # Variable for 'From'
        to_var = variable_mapping[to_value]      # Variable for 'To'

        # CONSTRUCT clause: map 'From' class to 'To' class
        if pd.notna(to_value):
            construct_statements.append(f"{from_var} rdf:type ex:{to_value}.")

        # Add relationships between the variables
        if pd.notna(relation_value) and relation_value != '-' and pd.notna(target_value) and target_value != '-':
            target_var = variable_mapping[df_main.loc[df_main['To'] == target_value, 'From'].values[0]]  # Reuse the variable for the 'Target'
            construct_statements.append(f"{from_var} ex:{relation_value} {target_var}.")

    # Now, use the second DataFrame to add relationships between entities in the WHERE clause
    for _, row in df_relationships.iterrows():
        subject_value = row['subject_label']
        predicate_value = row['predicate_label']
        object_value = row['object_label']

        subject_var = variable_mapping[subject_value]  # Variable for subject
        object_var = variable_mapping[object_value]    # Variable for object

        # WHERE clause: relationships from the second dataframe
        where_statements.append(f"{subject_var} ex:{predicate_value} {object_var}.")

    # Remove duplicates in both blocks
    construct_statements = list(dict.fromkeys(construct_statements))
    where_statements = list(dict.fromkeys(where_statements))

    # Construct the final output
    construct_block = "\n\t".join(construct_statements)
    where_block = "\n\t".join(where_statements)

    final_output = f"""
CONSTRUCT {{
\t{construct_block}
}} 

WHERE {{
\t{where_block}
}}
"""
    return final_output.strip()


def sparql_query_text_from_dataframe(df):
    # Forward fill '-' values in 'From' and 'To' columns to copy previous row's value
    df['From'] = df['From'].replace('-', pd.NA).ffill()
    df['To'] = df['To'].replace('-', pd.NA).ffill()

    # Collect all unique entities from 'From', 'To', and 'Target' columns
    unique_entities = pd.concat([df['From'], df['To'], df['Target']]).dropna().unique()

    # Generate dynamic variable names for unique entities (same variable for 'From' and 'To')
    variable_mapping = generate_variable_names(unique_entities)

    # Lists to store the 'some' declarations and the relation statements
    construct_statements = []
    where_statements = []

    # Generate the CONSTRUCT and WHERE statements
    for _, row in df.iterrows():
        from_value = row['From']
        to_value = row['To']
        relation_value = row['Relation']
        target_value = row['Target']

        # Use the same variable for both 'From' and 'To'
        from_var = variable_mapping[from_value]
        to_var = variable_mapping[from_value]  # Use the 'from_value' variable for 'To' as well

        # Add CONSTRUCT statements for "To" terms and relationships
        if pd.notna(to_value):
            construct_statements.append(f"{to_var} a {to_value}.")

        if pd.notna(target_value) and target_value != '-' and pd.notna(relation_value) and relation_value != '-':
            construct_statements.append(
                f"{to_var} {relation_value} {variable_mapping[target_value]}."
            )

    # Generate WHERE statements for all unique From entities
    for from_value in df['From'].dropna().unique():
        where_statements.append(f"{variable_mapping[from_value]} a {from_value}.")

    # Remove duplicates in both blocks
    construct_statements = list(dict.fromkeys(construct_statements))
    where_statements = list(dict.fromkeys(where_statements))

    # Construct the final output
    construct_block = "\n\t".join(construct_statements)
    where_block = "\n\t".join(where_statements)

    final_output = f"""
CONSTRUCT {{
\t{construct_block}
}}

WHERE {{
\t{where_block}
}}
"""
    return final_output.strip()


def extract_prefixes_from_sparql(sparql_query):
    """
    Extracts prefixes from the given SPARQL query.
    """
    prefix_pattern = r"PREFIX\s+(\w+):\s+<([^>]+)>"
    matches = re.findall(prefix_pattern, sparql_query)
    return matches


def generate_shacl_prefix_block(prefixes):
    """
    Generates the SHACL 'sh:prefixes' block for the given list of prefixes.
    """
    shacl_prefix_block = """
    sh:prefixes [
    """
    for prefix, namespace in prefixes:
        shacl_prefix_block += f"""
        sh:declare [
            sh:prefix "{prefix}" ;
            sh:namespace "{namespace}" ;
        ] ;
        """
    shacl_prefix_block += "\n    ] ;"
    return shacl_prefix_block.strip()



# excel_file = "./SHARC_tests.xlsx"  # Replace with the actual file path
# df = pd.read_excel(excel_file, sheet_name=None)
# classes_df = df['Curies']
# shape_validation_df = df['Shape Validation']
# shape_bridge_df = df['Shape Bridge']
#
# # Process the raw data
# raw_graph_data = shape_bridge_df[['From', 'To', 'Relation', 'Target']].values.tolist()
# graph_data = preprocess_graph_data(raw_graph_data)
#
# # Create a directed graph
# G = nx.DiGraph()
#
# # Add edges from graph_data, skip if "Target" is empty
# for row in graph_data:
#     from_node, to_node, relation, target_node = row
#     if target_node != "":
#         G.add_edge(to_node, target_node)
#
# # Find the longest path in the graph
# longest_path = find_longest_path(G)
#
# # Create a directed graph
# G_1 = nx.DiGraph()
#
# graph_data_1 = shape_validation_df[['subject_label', 'predicate_label', 'object_label']].values.tolist()
# # Add edges from graph_data
# for subject, predicate, obj in graph_data_1:
#     G_1.add_edge(subject, obj, label=predicate)  # Add edges with the predicate as label
#
# # Find the longest path in the graph
# longest_path_i1 = find_longest_path_1(G_1)
#
# mermaid_chart = """flowchart TD \n"""
#
# # Usage
# common_entries_sb_2 = deepcopy(process_shape_bridge(classes_df, shape_bridge_df))
# common_entries_sv_2 = deepcopy(process_shape_validation(classes_df, shape_validation_df))
#
# # Get the common entries and unique entries for shape_validation and shape_bridge
# common_entries, sv_specific, sb_specific = process_and_compare_entries(classes_df, shape_bridge_df, shape_validation_df)
#
# for label, curie in zip(common_entries['label'], common_entries['curie']):
#     mermaid_chart += f"    {curie}[{label}]\n"
# for label, curie in zip(sv_specific['label'], sv_specific['curie']):
#     mermaid_chart += f"    {curie}([{label}])\n"
# for label, curie in zip(sb_specific['label'], sb_specific['curie']):
#     mermaid_chart += f"    {curie}({label})\n"
#
# # Generate ShapeValidation section
# mermaid_chart += "\n    subgraph ShapeValidation\n        subgraph CoreShapeInformation\n"
# # find columns in shpaevalidation_df where both subject_label and object_label are in common_entries['label']
# mermaid_chart_1 = ""
# mermaid_chart_2 = ""
# line_arrow = "-"*(len(longest_path))+">"
# for subj, pred, obj in zip(shape_validation_df['subject_label'], shape_validation_df['predicate_label'], shape_validation_df['object_label']):
#     subj_curie = classes_df[classes_df['label'] == subj]['curie'].values[0]
#     obj_curie = classes_df[classes_df['label'] == obj]['curie'].values[0]
#     if subj in common_entries['label'].values and obj in common_entries['label'].values:
#         mermaid_chart_1 += f"        {subj_curie} ==>|{pred}| {obj_curie}\n"
#     else:
#         mermaid_chart_2 += f"    {subj_curie} {line_arrow}|{pred}| {obj_curie}\n"
# mermaid_chart += mermaid_chart_1
# mermaid_chart += "        end\n\n"
# mermaid_chart += mermaid_chart_2
# mermaid_chart += "    end\n\n"
# mermaid_chart += "    subgraph TransformedGraph\n"
#
# temp_from = []
# temp_to = []
# temp_relation = []
# temp_target = []
# mermaid_chart_3 = ""
# mermaid_chart_4 = ""
# for from_node, to_node, relation, target in zip(shape_bridge_df['From'], shape_bridge_df['To'], shape_bridge_df['Relation'], shape_bridge_df['Target']):
#     if not from_node == to_node:
#         temp_from = from_node
#         temp_to = to_node
#         dotted_arrow = "-"+"."*(len(longest_path_i1)+len(longest_path)-1)+"->"
#         mermaid_chart_4 += f"    {classes_df[classes_df['label'] == temp_from]['curie'].values[0]} {dotted_arrow}|SHACL_bridge| {classes_df[classes_df['label'] == temp_to]['curie'].values[0]}\n"
#     if relation == target:
#         continue
#     mermaid_chart_3 += f"    {classes_df[classes_df['label'] == temp_to]['curie'].values[0]} -->|{relation}| {classes_df[classes_df['label'] == target]['curie'].values[0]}\n"
#
# mermaid_chart += mermaid_chart_3
# mermaid_chart += "    end\n\n"
# mermaid_chart += mermaid_chart_4
#
# # export the mermaid chart as a txt file
# with open("./mermaid_chart.txt", "w") as f:
#     f.write(mermaid_chart)
Class_df = pd.DataFrame({'label': ['Process', 'ProcessStep', 'Input', 'InputSettings', 'ChemicalInvestigation', 'Setup', 'realizedOccurent', 'Specimen', 'Experiment', 'ExperimentSetup', 'Sample', 'Parameters'],
                          'curie': ['ex:Process', 'ex:ProcessStep', 'ex:Input', 'ex:InputSettings', 'ex:ChemicalInvestigation', 'ex:Setup', 'ex:realizedOccurent', 'ex:Specimen', 'ex:Experiment', 'ex:ExperimentSetup', 'ex:Sample', 'ex:Parameters']
                         })
Relation_df = pd.DataFrame({'label': ['isSome', 'hasPart', 'isSome', 'describes', 'isInput', 'hasModifier', 'is_a', 'hasExperimentSetup', 'hasSample', 'performedWith', 'hasConcentrations'],
                          'curie': ['ex:isSome', 'ex:hasPart', 'ex:isSome', 'ex:describes', 'ex:isInput', 'ex:hasModifier', 'ex:is_a', 'ex:hasExperimentSetup', 'ex:hasSample', 'ex:performedWith', 'ex:hasConcentrations']
                           })
shape_validation_df = pd.DataFrame({'subject_label':['Process', 'Process', 'Process', 'ProcessStep', 'Input', 'Input', 'Input'],
                                    'predicate_label':['isSome', 'hasPart', 'isSome', 'describes', 'isInput', 'hasModifier', 'is_a'],
                                    'object_label':['ChemicalInvestigation', 'ProcessStep', 'realizedOccurent', 'Setup', 'ProcessStep', 'InputSettings', 'Specimen']
                                   })
bridging_df = pd.DataFrame({'From':['Process', '-', 'ProcessStep', 'Input', 'InputSettings'],
                            'To':['Experiment', '-', 'ExperimentSetup', 'Sample', 'Parameters'],
                            'Relation':['hasExperimentSetup', 'hasSample', 'performedWith', 'hasConcentrations', '-'],
                            'Target':['ExperimentSetup', 'Sample', 'Parameters', 'Parameters', '-']
                           })
def generate_mermaid_chart_from_dfs(classes_df,relations_df, shape_validation_df, shape_bridge_df):
    # Load the data from the Excel

    # Process the raw data from shape bridge
    raw_graph_data = shape_bridge_df[['From', 'To', 'Relation', 'Target']].values.tolist()
    graph_data = preprocess_graph_data(raw_graph_data)  # Define this function based on your use case

    # Create a directed graph for the bridge
    G = nx.DiGraph()

    # Add edges from graph_data, skip if "Target" is empty
    for row in graph_data:
        from_node, to_node, relation, target_node = row
        if target_node != "":
            G.add_edge(to_node, target_node)

    # Find the longest path in the graph
    longest_path = find_longest_path(G)  # Ensure to define this function

    # Create a directed graph for shape validation
    G_1 = nx.DiGraph()
    graph_data_1 = shape_validation_df[['subject_label', 'predicate_label', 'object_label']].values.tolist()

    # Add edges from graph_data_1
    for subject, predicate, obj in graph_data_1:
        G_1.add_edge(subject, obj, label=predicate)

    # Find the longest path in the validation graph
    longest_path_i1 = find_longest_path_1(G_1)  # Ensure to define this function

    # Initialize the Mermaid chart
    mermaid_chart = """flowchart TD \n"""

    # Process shape bridge and shape validation
    common_entries_sb_2 = deepcopy(process_shape_bridge(classes_df, shape_bridge_df))
    common_entries_sv_2 = deepcopy(process_shape_validation(classes_df, shape_validation_df))

    # Get the common entries and unique entries for shape_validation and shape_bridge
    common_entries, sv_specific, sb_specific = process_and_compare_entries(classes_df, shape_bridge_df,
                                                                           shape_validation_df)

    # Add class labels and Curies to the chart
    for label, curie in zip(common_entries['label'], common_entries['curie']):
        mermaid_chart += f"    {curie}[{label}]\n"
    for label, curie in zip(sv_specific['label'], sv_specific['curie']):
        mermaid_chart += f"    {curie}([{label}])\n"
    for label, curie in zip(sb_specific['label'], sb_specific['curie']):
        mermaid_chart += f"    {curie}({label})\n"

    # Generate ShapeValidation section
    mermaid_chart += "\n    subgraph ShapeValidation\n        subgraph CoreShapeInformation\n"

    mermaid_chart_1 = ""
    mermaid_chart_2 = ""
    line_arrow = "-" * (len(longest_path)) + ">"

    for subj, pred, obj in zip(shape_validation_df['subject_label'], shape_validation_df['predicate_label'],
                               shape_validation_df['object_label']):
        subj_curie = classes_df[classes_df['label'] == subj]['curie'].values[0]
        obj_curie = classes_df[classes_df['label'] == obj]['curie'].values[0]
        if subj in common_entries['label'].values and obj in common_entries['label'].values:
            mermaid_chart_1 += f"        {subj_curie} ==>|{pred}| {obj_curie}\n"
        else:
            mermaid_chart_2 += f"    {subj_curie} {line_arrow}|{pred}| {obj_curie}\n"
    mermaid_chart += mermaid_chart_1
    mermaid_chart += "        end\n\n"
    mermaid_chart += mermaid_chart_2
    mermaid_chart += "    end\n\n"

    # Generate TransformedGraph section
    mermaid_chart += "    subgraph TransformedGraph\n"
    mermaid_chart_3 = ""
    mermaid_chart_4 = ""

    for from_node, to_node, relation, target in zip(shape_bridge_df['From'], shape_bridge_df['To'],
                                                    shape_bridge_df['Relation'], shape_bridge_df['Target']):
        if not from_node == to_node:
            temp_from = from_node
            temp_to = to_node
            dotted_arrow = "-" + "." * (len(longest_path_i1) + len(longest_path) - 1) + "->"
            mermaid_chart_4 += f"    {classes_df[classes_df['label'] == temp_from]['curie'].values[0]} {dotted_arrow}|SHACL_bridge| {classes_df[classes_df['label'] == temp_to]['curie'].values[0]}\n"
        if relation == target:
            continue
        mermaid_chart_3 += f"    {classes_df[classes_df['label'] == temp_to]['curie'].values[0]} -->|{relation}| {classes_df[classes_df['label'] == target]['curie'].values[0]}\n"

    mermaid_chart += mermaid_chart_3
    mermaid_chart += "    end\n\n"
    mermaid_chart += mermaid_chart_4

    # Export the mermaid chart to a text file
    with open("./mermaid_chart.txt", "w") as f:
        f.write(mermaid_chart)

    markdown_version_of_mermaid_chart = f"```mermaid \n{mermaid_chart}```"

    return mermaid_chart, markdown_version_of_mermaid_chart

mermaid_chart, markdown_version_of_mermaid_chart = generate_mermaid_chart_from_dfs(Class_df, Relation_df, shape_validation_df, bridging_df)
print(mermaid_chart)

def generate_shafe_from_dfs(classes_df,relations_df, shape_validation_df, shape_bridge_df):
    # Usage
    common_entries_sb_2 = deepcopy(process_shape_bridge(classes_df, shape_bridge_df))
    common_entries_sv_2 = deepcopy(process_shape_validation(classes_df, shape_validation_df))
    # Get the common entries and unique entries for shape_validation and shape_bridge
    common_entries, sv_specific, sb_specific = process_and_compare_entries(classes_df, shape_bridge_df, shape_validation_df)
    # create a df from the shape_validation_df where only columns with common entries are selected
    common_entries_2 = common_entries['label']
    common_entries_2 = common_entries_2.to_list()
    shape_validation_df_common = shape_validation_df[shape_validation_df['subject_label'].isin(common_entries_2) & shape_validation_df['object_label'].isin(common_entries_2)]
    # Usage
    process_graph_centrality(shape_validation_df_common)
    # Create a directed graph using networkx
    G = nx.DiGraph()

    # Add nodes and edges from the DataFrame
    for index, row in shape_validation_df.iterrows():
        subject = row['subject_label']
        predicate = row['predicate_label']
        obj = row['object_label']

        # Add edge to the graph (directed from subject to object)
        G.add_edge(subject, obj, predicate=predicate)

    # SHACL template to start with
    shacl_template = """
    @prefix : <http://example.org/ontology#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    
    :BridgeValidationSHAPE
        a sh:NodeShape ;
        sh:targetClass :Input ;  # The shape targets the Input class
    """
    # Generate the SHACL shapes from the graph analysis starting from 'Input'
    shacl_shapes = generate_nested_shacl(G, 'Input')
    # Final SHACL shape with template and generated properties
    final_shacl = shacl_template + shacl_shapes

    # Generate the text from the dataframe
    generated_text = sparql_query_text_from_dataframes(shape_bridge_df,shape_validation_df_common)

    # Example SPARQL query
    sparql_query = """
    PREFIX ex: <http://example.org/ontology#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    
    CONSTRUCT {
        ?variable_e a ex:Experiment.
        ?variable_f a ex:ExperimentSetup.
        ?variable_g a ex:Sample.
        ?variable_h a ex:Parameters.
        ?variable_e ex:hasExperimentSetup ?variable_f.
        ?variable_e ex:hasSample ?variable_g.
        ?variable_f ex:performedWith ?variable_h.
        ?variable_g ex:hasConcentrations ?variable_h.
    } 
    WHERE {
        ?variable_a a ex:Process.
        ?variable_b a ex:ProcessStep.
        ?variable_c a ex:Input.
        ?variable_d a ex:InputSettings.
    }
    """
    # prefixes = extract_prefixes_from_sparql(generated_text)
    # shacl_prefix_block = generate_shacl_prefix_block(prefixes)
    shacl_rule = f"""
    # SPARQL-based validation using sh:sparql
    sh:rule [
        a sh:SPARQLRule ;
        sh:prefixes [
            sh:declare [
                sh:prefix "ex" ;
                sh:namespace "http://example.org/ontology#" ;
            ] ;
            sh:declare [
                sh:prefix "rdf" ;
                sh:namespace "http://www.w3.org/1999/02/22-rdf-syntax-ns#" ;
            ] ;
            sh:declare [
                sh:prefix "rdfs" ;
                sh:namespace "http://www.w3.org/2000/01/rdf-schema#" ;
            ] ;
            sh:declare [
                sh:prefix "xsd" ;
                sh:namespace "http://www.w3.org/2001/XMLSchema#" ;
            ] ;
        ] ;
        sh:message "SPARQL rule for Input and associated properties." ;
        sh:construct \"\"\"\n
        {generated_text}\"\"\" ;
        ] ;
    .
    """

    final_shacl_2 = final_shacl + shacl_rule
    # Save to a file (if needed)
    with open('./shacl_validation_2.ttl', 'w') as f:
        f.write(final_shacl_2)

    return final_shacl_2

final_shacl_2 = generate_shafe_from_dfs(Class_df, Relation_df, shape_validation_df, bridging_df)

def gen_dif_and_ext_graph(data_g, shape_g):
    val_0 = Validator(data_g, options={"advanced": True, "inference": "rdfs"})
    conforms_data, report_g_data, report_text_data = val_0.run()
    inferred_base_graph_1 = val_0.target_graph
    val_1 = Validator(data_g, shacl_graph=shape_g, options={"advanced": True, "inference": "rdfs"})
    conforms_expanded, report_g_expanded, report_text_expanded = val_1.run()
    expanded_g = val_1.target_graph
    is0_1, is0_2 = to_isomorphic(inferred_base_graph_1), to_isomorphic(expanded_g)
    both, diff_g1, diff_g2 = graph_diff(is0_1, is0_2)
    conforms_sum = f'baseshape: \n{conforms_data}\nexpanded graph: \n{conforms_expanded}'
    dict_of_report_g = {'baseshape_report_graph': report_g_data, 'expanded_report_graph': report_g_expanded}
    report_text_sum = f'baseshape: \n{report_text_data}\nexpanded graph: \n{report_text_expanded}'
    return expanded_g, diff_g2, conforms_sum, dict_of_report_g, report_text_sum


path_to_data = "./test_ontology_and_data_4.ttl"
# path_to_shapes = "./test_shacl_sparql_1.ttl"
path_to_shapes = "./shacl_validation_2.ttl"

data_graph = Graph()
data_graph.parse(path_to_data, format="ttl")

shape_graph = Graph()
shape_graph.parse(path_to_shapes, format="ttl")

expanded_graph, diff_graph, conforms, report_graph_dict, report_text = gen_dif_and_ext_graph(data_graph, shape_graph)
expanded_graph.serialize(destination='./expanded_graph.ttl', format='turtle')
diff_graph.serialize(destination='./diff_graph.ttl', format='turtle')