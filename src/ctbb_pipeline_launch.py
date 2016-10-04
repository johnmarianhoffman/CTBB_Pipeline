import sys
import os

import yaml
import logging

from ctbb_pipeline_library import ctbb_pipeline_library as ctbb_plib
import pypeline as pype
from pypeline import mutex

def usage():
    logging.info('usage: ctbb_pipeline_launch.py /path/to/config/file.yaml')
    logging.info('    Copyright (c) John Hoffman 2016')

def load_config(filepath):

    logging.info('Loading configuration file: %s' % filepath)

    # Load pipeline run from YAML configuration file 
    with open(sys.argv[1],'r') as f:
        yml_string=f.read();

    config_dict=yaml.load(yml_string)

    # We only require that a case list and output library be defined
    if ('case_list' not in config_dict.keys()) or ('library' not in config_dict.keys()):
        logging.error('"case_list" and "library" are required fields in ctbb_pipeline configuration file and one or the other was not found. Exiting."')
        config_dict={}

    else:
        # Check for optional fields. Set to defaults as needed.
        # Doses
        if ('doses' not in config_dict.keys()):
            config_dict['doses']=[100,10]
        
        # Slice Thickness
        if ('slice_thickness' not in config_dict.keys()):
            config_dict['slice_thickness']=[0.6,5.0]

        # Kernel
        if ('kernels' not in config_dict.keys()):
            config_dict['kernels']=[1,3]

        if not os.path.isdir(config_dict['library']):
            os.makedirs(config_dict['library'])
            logging.warning('Library directory does not exist, creating.')
            
        # Verify that the case list and library directory exist
        if not os.path.exists(config_dict['case_list']):
            logging.error('Specified case_list does not exist. Exiting.')
            config_dict={}
            
    return config_dict

def flush_jobs_to_queue(config,case_list,library):
    # inputs are:
    #     config    - config dictionary from load_config
    #     case_list - case list object
    #     library   - library object
    
    queue_strings=[]
            
    m=mutex('queue',library.mutex_dir)
    m.lock()
    
    ## Form the strings to be written
    for c in case_list.case_list:
        if not c:
            continue
        for dose in config['doses']:
            for st in config['slice_thicknesses']:
                for kernel in config['kernels']:
                    queue_strings.append(('%s,%s,%s,%s\n') % (c,dose,kernel,st));
    
    queue_file=os.path.join(library.path,'.proc','queue')

    priority = 'normal'
    
    ## If priority "normal" write to end of file
    if priority == 'normal':
        with open(queue_file,'a') as f:
            for q_string in queue_strings:
                f.write(q_string)
    
    ## If priority "high" write to beginning of file
    ## Read queue into memory
    elif priority == 'high':
        with open(queue_file,'r') as f:
            existing_queue=f.read()
        
        ## Pop new items into beginning of queue and then write rest of queue back
        with open(queue_file,'w') as f:
            for q_string in queue_strings:
                f.write(q_string)
            f.write(existing_queue)
    
    ## Handle any weirdness
    else:
        logging.error('Unknown queue priority request')
    
    m.unlock()

if __name__=='__main__':
    status = 0

    run_dir=os.path.dirname(os.path.abspath(__file__))
    
    if (len(sys.argv) < 2):
        usage()
    else:
        filepath=sys.argv[1]
                 
    if not os.path.exists(filepath):        
        logging.error('Configuration file not found! Exiting.')
        status=1
    else:
        config=load_config(filepath)

        # Configuration loaded properly
        if config:

            # Instantiate library in library directory
            library=ctbb_plib(config['library']);
            
            # Get PRMBs from raw files
            case_list=pype.case_list(config['case_list'])
            case_list.get_prmbs()

            # Flush PRMBs to pipeline library
            for i in range(len(case_list.prmbs_raw)):
                output_file_name=os.path.basename(case_list.case_list[i])+'.prmb'
                output_dir_name=os.path.join(library.path,'raw')
                output_fullpath=os.path.join(output_dir_name,output_file_name);

                with open(output_fullpath,'w') as f:
                    f.write(case_list.prmbs_raw[i])

            # Flush new jobs to the queue
            logging.info('Sending jobs to queue')
            flush_jobs_to_queue(config,case_list,library)
    
            # Launch the daemon in the background
            logging.info('Launching pipeline daemon')
            command="python %s/ctbb_pipeline_daemon.py %s" % (run_dir,library.path)
            os.system("nohup %s >/dev/null 2>&1 &" % command);
            
        # Configuration didn't load properly
        else:
            logging.error('Something went wrong parsing pipeline configuration file') 
            status=1

    sys.exit(status)
