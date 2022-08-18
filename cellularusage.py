#!/usr/bin/env python
"""
CGNX script to minimize cellular usage at one or more sites
tkamath@paloaltonetworks.com
"""
import sys
import os
import argparse
import cloudgenix

SCRIPT_NAME = "Minimize Cellular Usage"
SCRIPT_VERSION = "v1.0"


# Import CloudGenix Python SDK
try:
    import cloudgenix
except ImportError as e:
    cloudgenix = None
    sys.stderr.write("ERROR: 'cloudgenix' python module required. (try 'pip install cloudgenix').\n {0}\n".format(e))
    sys.exit(1)

# Check for cloudgenix_settings.py config file in cwd.
sys.path.append(os.getcwd())
try:
    from cloudgenix_settings import CLOUDGENIX_AUTH_TOKEN

except ImportError:
    # if cloudgenix_settings.py file does not exist,
    # Get AUTH_TOKEN/X_AUTH_TOKEN from env variable, if it exists. X_AUTH_TOKEN takes priority.
    if "X_AUTH_TOKEN" in os.environ:
        CLOUDGENIX_AUTH_TOKEN = os.environ.get('X_AUTH_TOKEN')
    elif "AUTH_TOKEN" in os.environ:
        CLOUDGENIX_AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
    else:
        # not set
        CLOUDGENIX_AUTH_TOKEN = None

try:
    # Also, separately try and import USERNAME/PASSWORD from the config file.
    from cloudgenix_settings import CLOUDGENIX_USER, CLOUDGENIX_PASSWORD

except ImportError:
    # will get caught below
    CLOUDGENIX_USER = None
    CLOUDGENIX_PASSWORD = None


# Handle differences between python 2 and 3. Code can use text_type and binary_type instead of str/bytes/unicode etc.
if sys.version_info < (3,):
    text_type = unicode
    binary_type = str
else:
    text_type = str
    binary_type = bytes



def cleanexit(cgx_session):
    print("INFO: Logging Out")
    cgx_session.get.logout()
    sys.exit()



site_id_name = {}
site_name_id = {}
nw_id_name = {}
label_id_name = {}
label_name_id = {}
siteid_swilist = {}
dcsites = []

def create_dicts(cgx_session, sitename, labels):
    print("Creating Translation Dicts")
    #
    # Get Sites
    #
    print("\tSites")
    resp = cgx_session.get.sites()
    if resp.cgx_status:
        sitelist = resp.cgx_content.get("items", None)
        for site in sitelist:
            site_id_name[site["id"]] = site["name"]
            site_name_id[site["name"]] = site["id"]

            if site["element_cluster_role"] == "HUB":
                dcsites.append(site["id"])

    else:
        print("ERR: Could not retrieve Sites")
        cloudgenix.jd_detailed(resp)

    #
    # Validate Site Name Passed
    #
    sitelist = []
    if sitename == "ALL_SITES":
        sitelist = site_id_name.keys()

    elif sitename in site_name_id.keys():
        sitelist = [site_name_id[sitename]]

    else:
        print("ERR: Invalid Site Name: {}. Please re-enter sitename".format(sitename))
        cleanexit(cgx_session)

    #
    # Get WAN Interface Labels
    #
    print("\tWAN Interface Labels")
    resp = cgx_session.get.waninterfacelabels()
    if resp.cgx_status:
        itemlist = resp.cgx_content.get("items", None)
        for item in itemlist:
            label_id_name[item["id"]] = item["name"]
            label_name_id[item["name"]] = item["id"]
    else:
        print("ERR: Could not retrieve WAN Interface Labels")
        cloudgenix.jd_detailed(resp)

    #
    # Validate Label passed
    #
    labellist = []
    for label in labels:
        if label == "ALL_LABELS":
            labellist = label_id_name.keys()

        elif label in label_name_id.keys():
            labellist.append(label_name_id[label])

        else:
            print("ERR: Invalid Label Name: {}. Please re-enter labels".format(label))
            cleanexit(cgx_session)

    #
    # Get WAN Networks
    #
    print("\tWAN Networks")
    resp = cgx_session.get.wannetworks()
    if resp.cgx_status:
        nws = resp.cgx_content.get("items", None)
        for nw in nws:
            nw_id_name[nw["id"]] = nw["name"]
    else:
        print("ERR: Could not retrieve WAN Networks")
        cloudgenix.jd_detailed(resp)

    return sitelist, labellist


def go():
    """
    Stub script entry point. Authenticates CloudGenix SDK, and gathers options from command line to run do_site()
    :return: No return
    """

    # Parse arguments
    parser = argparse.ArgumentParser(description="{0} ({1})".format(SCRIPT_NAME, SCRIPT_VERSION))

    ####
    #
    # Add custom cmdline argparse arguments here
    #
    ####

    custom_group = parser.add_argument_group('custom_args', 'My Custom Args')
    custom_group.add_argument("--print-lower", help="Print all in lower case",
                              default=False, action="store_true")

    ####
    #
    # End custom cmdline arguments
    #
    ####

    # Standard CloudGenix script switches.
    controller_group = parser.add_argument_group('API', 'These options change how this program connects to the API.')
    controller_group.add_argument("--controller", "-C",
                                  help="Controller URI, ex. https://api.elcapitan.cloudgenix.com",
                                  default=None)

    login_group = parser.add_argument_group('Login', 'These options allow skipping of interactive login')
    login_group.add_argument("--email", "-E", help="Use this email as User Name instead of cloudgenix_settings.py "
                                                   "or prompting",
                             default=None)
    login_group.add_argument("--password", "-PW", help="Use this Password instead of cloudgenix_settings.py "
                                                       "or prompting",
                             default=None)
    login_group.add_argument("--insecure", "-I", help="Do not verify SSL certificate",
                             action='store_true',
                             default=False)
    login_group.add_argument("--noregion", "-NR", help="Ignore Region-based redirection.",
                             dest='ignore_region', action='store_true', default=False)

    debug_group = parser.add_argument_group('Debug', 'These options enable debugging output')
    debug_group.add_argument("--sdkdebug", "-D", help="Enable SDK Debug output, levels 0-2", type=int,
                             default=0)
    config_group = parser.add_argument_group('Config', 'These options are to provide site and BW monitoring details')
    config_group.add_argument("--sitename", "-S", help="Name of the Site. Or use keyword ALL_SITES", default="ALL_SITES")
    config_group.add_argument("--label", "-L",
                              help="Circuit Label to minimize cellular usage on. Provide one or more circuit labels or use the keyword ALL_LABELS",
                              default=None)

    ############################################################################
    # Parse arguments provided via CLI
    ############################################################################
    args = vars(parser.parse_args())
    sdk_debuglevel = args["sdkdebug"]
    sitename = args["sitename"]
    label = args["label"]
    labels = []
    if label is None:
        print("ERR: Invalid label. Please provide one or more labels or use the keyword ALL_LABELS")
        sys.exit()
    else:
        if label == "ALL_LABELS":
            labels = ["ALL_LABELS"]

        elif "," in label:
            tmp = label.split(",")
            for item in tmp:
                labels.append(item)
        else:
            labels.append(label)


    if sitename is None:
        print("ERR: No site name provided. Please provide a site name or use the keyword: ALL_SITES")
        sys.exit()

    ############################################################################
    # Instantiate API & Login
    ############################################################################
    cgx_session = cloudgenix.API(controller=args["controller"], ssl_verify=False)
    cgx_session.set_debug(sdk_debuglevel)
    print("{0} v{1} ({2})\n".format(SCRIPT_NAME, cgx_session.version, cgx_session.controller))

    # login logic. Use cmdline if set, use AUTH_TOKEN next, finally user/pass from config file, then prompt.
    # figure out user
    if args["email"]:
        user_email = args["email"]
    elif CLOUDGENIX_USER:
        user_email = CLOUDGENIX_USER
    else:
        user_email = None

    # figure out password
    if args["password"]:
        user_password = args["password"]
    elif CLOUDGENIX_PASSWORD:
        user_password = CLOUDGENIX_PASSWORD
    else:
        user_password = None

    # check for token
    if CLOUDGENIX_AUTH_TOKEN and not args["email"] and not args["password"]:
        cgx_session.interactive.use_token(CLOUDGENIX_AUTH_TOKEN)
        if cgx_session.tenant_id is None:
            print("AUTH_TOKEN login failure, please check token.")
            sys.exit()

    else:
        while cgx_session.tenant_id is None:
            cgx_session.interactive.login(user_email, user_password)
            # clear after one failed login, force relogin.
            if not cgx_session.tenant_id:
                user_email = None
                user_password = None
    ############################################################################
    # Create Translation Dicts
    ############################################################################
    sitelist, labellist = create_dicts(cgx_session, sitename, labels)

    ############################################################################
    # Disable Bandwidth Monitoring
    ############################################################################
    print("INFO: Retrieving circuits")
    for sid in sitelist:
        sname = site_id_name[sid]
        print("\nSite: {}\n".format(sname))

        resp = cgx_session.get.waninterfaces(site_id=sid)
        if resp.cgx_status:
            swilist = resp.cgx_content.get("items", None)

            for swi in swilist:
                cname = swi["name"]
                if swi["name"] is None:
                    cname = "{}_{}".format(nw_id_name[swi["network_id"]], label_id_name[swi["label_id"]])

                if swi["label_id"] in labellist:
                    #
                    # DC Config
                    #
                    if sid in dcsites:
                        if (swi["vpnlink_configuration"] == {"keep_alive_failure_count": 3, "keep_alive_interval": 1740000}):
                            print("\tSkipped [Config Uptodate]: WAN Interface: {} ".format(cname))

                        else:
                            swi["vpnlink_configuration"] = {"keep_alive_failure_count": 3,
                                                            "keep_alive_interval": 1740000}

                            resp = cgx_session.put.waninterfaces(site_id=sid, waninterface_id=swi["id"], data=swi)
                            if resp.cgx_status:
                                print("\tConfigured: WAN Interface: {}".format(cname))

                            else:
                                print("\tERR: Could not update WAN Interface {}".format(cname))
                                cloudgenix.jd_detailed(resp)

                    #
                    # Branch Config
                    #
                    else:

                        if ((swi["use_for_application_reachability_probes"] == False) and (swi["use_for_controller_connections"] == False) and (swi["vpnlink_configuration"] == {"keep_alive_failure_count": 3, "keep_alive_interval": 1740000})):
                            print("\tSkipped [Config Uptodate]: WAN Interface: {} ".format(cname))

                        else:
                            swi["use_for_application_reachability_probes"] = False
                            swi["use_for_controller_connections"] = False
                            swi["vpnlink_configuration"] = {"keep_alive_failure_count": 3, "keep_alive_interval": 1740000}

                            resp = cgx_session.put.waninterfaces(site_id=sid, waninterface_id=swi["id"], data=swi)
                            if resp.cgx_status:
                                print("\tConfigured: WAN Interface: {}".format(cname))

                            else:
                                print("\tERR: Could not update WAN Interface {}".format(cname))
                                cloudgenix.jd_detailed(resp)
                else:
                    print("\tSkipped [Label  Mismatch]: WAN Interface: {}".format(cname, sname))
        else:
            print("ERR: Could not retrieve WAN Interfaces for site {}".format(sname))
            cloudgenix.jd_detailed(resp)

    ############################################################################
    # Logout to clear session.
    ############################################################################
    cleanexit(cgx_session)


if __name__ == "__main__":
    go()
