"""Clarify input campaign identity independently of original-parent lineage."""
from common import Inputs,CAMPAIGN,CAMPAIGN_ID,HERE
from pathlib import Path

class PilotInputs(Inputs):
    def __init__(self,current_campaign=None):
        super().__init__();self.current_campaign=Path(current_campaign).resolve() if current_campaign is not None else None
    def ref(self,path,role,read_mode='hash_only',expected=None):
        row=super().ref(path,role,read_mode,expected)
        if row is None:return row
        p=Path(path).resolve();row['original_parent_campaign_id']=CAMPAIGN_ID
        if p.is_relative_to(CAMPAIGN.resolve()):row['campaign_id']=CAMPAIGN_ID
        elif self.current_campaign is not None and p.is_relative_to(self.current_campaign):row['campaign_id']=self.current_campaign.name
        else:row['campaign_id']=None
        row['implementation_version']='85_onset_reuse_pilot_v1'
        return row
