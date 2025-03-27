#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

from ovsdbapp.backend.ovs_idl import connection, idlutils
from ovsdbapp.schema.open_vswitch import impl_idl as ovs_impl_idl

import sys


SWITCH_NAME = "dsw-host"

class OVSDBManager:
    """Class for managing OVSDB connections and operations"""

    # Class constants
    OVS_CONNECTION = "unix:/tmp/ovs-forwarded.sock"
    OVSDB_CONNECTION_TIMEOUT = 30

    def __init__(self, auto_connect=True):
        """Initialize the OVSDB manager and establish connection if auto_connect is True"""
        self.conn = None
        self.ovs = None

        if auto_connect:
            try:
                self.connect()
            except Exception as e:
                print(f"Warning: Failed to connect automatically: {e}")
                print(
                    "You'll need to call connect() manually before using other methods."
                )

    def connect(self):
        """Establish a connection to Open vSwitch via Unix socket"""
        helper = idlutils.get_schema_helper(self.OVS_CONNECTION, "Open_vSwitch")
        # print(f"Helper: {json.dumps(helper.schema_json)}")
        helper.register_all()
        idl = connection.OvsdbIdl(self.OVS_CONNECTION, helper)
        self.conn = connection.Connection(
            idl=idl, timeout=self.OVSDB_CONNECTION_TIMEOUT
        )
        self.ovs = ovs_impl_idl.OvsdbIdl(self.conn)
        return self.ovs
    
    def _get_switches(self)->list:
        try:
            # Get all existing bridges
            sw_list = self.ovs.list_br().execute(check_error = True)
            return sw_list
        except Exception as e:
            print(f"Error retrieving bridges: {e}")
            return []
        
    def get_taps(self, switch=SWITCH_NAME)->list:
        try:
            ports_list = self.ovs.list_ports(bridge=switch).execute(check_error = True)
            return ports_list
        except Exception as e:
            return []
            
    def get_tap(self, tap_name: str)->dict:
        try:
            ports = self.get_taps()
            if not tap_name in ports:
                return {}
            
            tap_details = self.ovs.db_find("Port", ("name", "=", tap_name)).execute(check_error = True)
            
            return tap_details[0]
        
        except Exception as e:
            return {}
             
    def set_tap(
        self,
        tap_name: str,
        vlan_mode: str,
        tag: int,
        trunks: list[int]
    )->bool:
        cur_conf = self.get_tap(tap_name)
        print(f"cur_conf: {cur_conf}")
        if cur_conf:
            try:
                if cur_conf["vlan_mode"] != vlan_mode:
                    print(f"Setting vlan_mode to {vlan_mode} from {cur_conf['vlan_mode']}")
                    res = self.ovs.db_set("Port", tap_name, ("vlan_mode", vlan_mode)).execute(check_error = True)
                    print(f"Result: {res}")
                if cur_conf["tag"] != tag and vlan_mode == "access":
                    print(f"Setting tag to {tag} from {cur_conf['tag']}")
                    res = self.ovs.db_set("Port", tap_name, ("tag", tag)).execute(check_error = True)
                    print(f"Result: {res}")
                if cur_conf["trunks"] != trunks and vlan_mode == "trunks":
                    print(f"Setting trunks to {trunks} from {cur_conf['trunks']}")
                    res = self.ovs.db_set("Port", tap_name, ("trunks", trunks)).execute(check_error = True)
                    print(f"Result: {res}")
                return True
            except Exception as e:
                raise SystemExit(f"Failed to set tap {tap_name}: {e}")
        else:
            raise SystemExit(f"Tap {tap_name} not found")