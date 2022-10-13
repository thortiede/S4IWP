import os
import json


from pysbml4j import Sbml4j
from pysbml4j import Configuration

import logging
from logging.config import fileConfig
import configparser

# Initialize logging system
configFolder = "/config"
fileConfig('{}/logging-config.ini'.format(configFolder))
logger = logging.getLogger()
logging.getLogger("chardet.charsetprober").disabled = True


if __name__ == "__main__":
    # read config
    config = configparser.ConfigParser()
    config.read('{}/s4iwp.ini'.format(configFolder))
    server_conf = config['server']
    host = server_conf.get('host')
    port = server_conf.get('port')
    if not host.startswith('http'):
        host = "{}{}".format("http://", host)
    logger.debug(f"Host is {host}:{port}")
    client = Sbml4j(Configuration(host, port, server_conf.get('application_context')))
    
    data_conf = config['data']
    sbml_dir = data_conf.get("sbml_dir")

    source_conf = config['source']
    source_name = source_conf.get('name')
    source_version = source_conf.get('version')
    source_org = source_conf.get('orgCode')

    target_conf = config['target']
    
    hasTransformation = False
    transformation_conf = config['transformation']
    if transformation_conf != None:
        hasTransformation = True
        transformation_meta = dict()
        transformation_dict = {"transformation": dict()}
        transformation_steps_string = transformation_conf.get("steps")
        transformation_path = transformation_conf.get("path")
        if transformation_steps_string != None:
            transformation_steps = transformation_steps_string.split(',')
            for step in transformation_steps:
                with open(os.path.join(transformation_path, step), "r") as t:
                    step_dict = json.loads(t.read())
                    transformation_meta[step] = step_dict
            transformation_dict["transformation"] = transformation_meta
                    
    origin_conf = config['origin']
    hasOrigin = False
    if origin_conf != None:
        origin_path = origin_conf.get("path")
        origin_file_suffix = origin_conf.get("file_suffix")
        hasOrigin = True

    pwuuids = []
    filelist = os.listdir(sbml_dir)

        
    logger.info("Uploading SBML files..")
    for file in filelist:
        if file.endswith("xml"):
            logger.debug("Processing file: {}".format(file))
            try:
                fullfilename = os.path.join(sbml_dir, file)
                resp = client.uploadSBML([fullfilename], source_org, source_name, source_version)
                
                uuid = resp.get(fullfilename).get("uuid")
                pwuuids.append(uuid)
            except:
                logger.error("Failed to presist model in: {}. Response was: {}".format(file, resp))
                
            # Do the metadata for the origin
            if hasOrigin:
                origin_prefix = file.split('.')[0]
                origin_file = '.'.join([origin_prefix, origin_file_suffix])
                origin_dict = dict()
                origin_dict["Original Filename"] = ".".join([origin_prefix, "xml"]) # This is previous knowledge, but ok for now
                with open(os.path.join(origin_path, origin_file), "r") as o:
                   
                    for line in o.readlines():
                        idx = line.find(':')
                        if idx < 0:
                            logger.warning(f"Cannot split origin entry {line} by :")
                            origin_dict[line] = line
                        else:
                            origin_dict[line[0:idx].strip()] = line[idx+1:].strip()
                
                # Find the file node for this pathway
                fileUUIDs = client.getFileorigin(uuid)
                if len(fileUUIDs) > 1:
                    logger.warning(f"Found multiple file sources for element with uuid {uuid}")
                elif len(fileUUIDs) < 1:
                    logger.warning(f"Found no sources for element with uuid {uuid}")
                for fileUUID in fileUUIDs:
                    # Add origin metadata
                    origin_resp = client.addProvenance(fileUUID, "origin", origin_dict)
                    logger.debug(f"Added origin provenance to file with uuid {fileUUID}")
                   
            if hasTransformation:
                # Do the metadata for KEGGtranslator
                for transformation_item in transformation_dict.keys():
                    transformation_resp = client.addProvenance(fileUUID, transformation_item, transformation_dict[transformation_item])
                    logger.debug(f"Added transfromation provenance for step {transformation_item} to file with uuid {fileUUID}")
                    
               
    # Create one pathway collection to derive the network mappings from
    logger.info("Creating pathway collection..")
    collUUID = client.createPathwayCollection(target_conf.get('collection_name'), target_conf.get('collection_desc'), pwuuids)

    # Create the network mappings that are configured
    logger.info("Creating network mappings..")
    mapping_types = target_conf.get('mapping_types').split(',')
    mapping_name_suffix = target_conf.get('mapping_name_suffix') 
    for mapping_type in mapping_types:
        logger.debug("Creating Mapping of type {} with name {}_{} for collection with UUID {}".format(mapping_type, mapping_type, mapping_name_suffix, collUUID))
        client.mapPathway(collUUID, mapping_type, "{}_{}".format(mapping_type, mapping_name_suffix))
        logger.info("Adding provenance info..")

    hasCsv = False
    # Upload the provided csv file
    try:
        csv_conf = config['csv']
        hasCsv = True
    except KeyError:
        logger.warning("No csv configuration found. Skipping csv annotation")
        
    
    if hasCsv:
        csv_folder = csv_conf.get('folder')
        csv_filename = csv_conf.get('filename')
        csv_annotation_type = csv_conf.get('annotation_type')
        csv_network_names_string = csv_conf.get('network_names')
        if csv_network_names_string != None :
            csv_network_names = csv_network_names_string.split(',')
        csv_status = 0
        if csv_folder == None or csv_folder == "":
            logger.warning("No csv folder configured")
            csv_status += 1
        elif csv_folder.endswith("/"):
            csv_path_sep = ""
        else:
            csv_path_sep = "/"
        if csv_filename == None or csv_filename == "":
            logger.warning("No csv filename configured")
            csv_status += 10
        if csv_annotation_type == None or csv_annotation_type == "":
            logger.warning("No csv annotation type configured")
            csv_status += 100
        if csv_network_names == None or csv_network_names == "":
            logger.warning("No csv network names configured")
            csv_status += 1000
            logger.info("Adding csv data to networks")
        if csv_status > 0:
            logger.info("Cannot add csv data to networks, status is {}".format(csv_status))
        else:
            csv_path = csv_folder + csv_path_sep + csv_filename
            prefix_mapping_name = False
            if len(csv_network_names) != len(mapping_types):
                 logger.warning("Not the same number of csv network-names configured as mapping_types generated. Using Annotation-Type as prefix")
                 prefix_mapping_name = True
    
            for i in range(len(mapping_types)):
                 mapping_type = mapping_types[i]
                 old_mapping_name = "{}_{}".format(mapping_type, mapping_name_suffix)
                 net = client.getNetworkByName(old_mapping_name)
                 if prefix_mapping_name:
                     new_mapping_name = "{}_{}".format(csv_annotation_type,old_mapping_name)
                 else:
                     new_mapping_name = csv_network_names[i]
                 # Add the csv data to the network
                 logger.debug("Uploading csv file {} of type {} to network of type {} to create network with name {}".format(csv_path, csv_annotation_type, mapping_type, new_mapping_name))
                 net.addCsvData(csv_path, csv_annotation_type, new_mapping_name) 

