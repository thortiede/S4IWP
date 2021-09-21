import os

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
    if not host.startswith('http'):
        host = "{}{}".format("http://", host)
    client = Sbml4j(Configuration(host, server_conf.get('port'), server_conf.get('application_context')))
    
    data_conf = config['data']
    sbml_dir = data_conf.get("sbml_dir")
    if not sbml_dir.endswith('/'):
        sbml_dir = "{}/".format(sbml_dir)
    source_conf = config['source']
    source_name = source_conf.get('name')
    source_version = source_conf.get('version')
    source_org = source_conf.get('orgCode')

    target_conf = config['target']
    csv_conf = config['csv']

    pwuuids = []
    filelist = os.listdir(sbml_dir)
    if sbml_dir.endswith("/"):
        sbml_path_sep = ""
    else:
        sbml_path_sep = "/"
    logger.info("Uploading SBML files..")
    for file in filelist:
        if file.endswith("xml"):
            logger.debug("Processing file: {}".format(file))
            try:
                fullfilename = "{}{}{}".format(sbml_dir,sbml_path_sep,file)
                resp = client.uploadSBML([fullfilename], source_org, source_name, source_version)
                pwuuids.append(resp.get(fullfilename).get("uuid"))
            except:
                logger.error("Failed to presist model in: {}. Response was: ".format(file, resp))

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

    # Upload the provided csv file
    csv_folder = csv_conf.get('folder')
    csv_filename = csv_conf.get('filename')
    csv_annotation_type = csv_conf.get('annotation_type')
    csv_network_names = csv_conf.get('network_names').split(',')
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

