"""The small, explicitly supported JSON Schema vocabulary for this release."""


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def array(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def build_schema():
    text = {"type": "string", "minLength": 1}
    string = {"type": "string"}
    ident = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,95}$"}
    revision = {"type": "integer", "minimum": 1}
    strings = array(text)
    mapping = {"type": "object", "additionalProperties": True}
    enum = lambda *values: {"enum": list(values)}
    base = {"id": ident, "revision": revision}
    defs = {}
    defs['rule'] = obj({'id': ident, 'description': text, 'parameters': mapping,
                        'verification': text})
    defs['contract'] = obj({**base, 'name': text,
                            'carrier': enum('file', 'dataframe', 'function', 'http', 'event', 'other'),
                            'format': text, 'schema': mapping,
                            'semantic_rules': array(ref('rule'), 1),
                            'error_behavior': text, 'side_effects': text,
                            'fingerprint': text})
    defs['port'] = obj({'id': ident, 'name': text, 'contract_id': ident,
                        'description': text})
    defs['architecture_review'] = obj({'reviewer': text,
                                       'review_mode': enum('self_review', 'independent'),
                                       'findings': text})
    defs['architecture'] = obj({**base, 'goal_id': ident, 'scope': array(text, 1),
                                'evidence_refs': array(text, 1), 'module_ids': array(ident, 1),
                                'root_module_ids': array(ident, 1), 'unresolved': strings,
                                'status': enum('draft', 'reviewed', 'baselined'),
                                'review': {'oneOf': [{'type': 'null'}, ref('architecture_review')]}})
    defs['product_module'] = obj({**base, 'architecture_id': ident,
                                  'parent_id': string, 'name': text,
                                  'kind': enum('existing', 'planned', 'external'),
                                  'responsibility': text, 'exclusions': strings,
                                  'implementation_refs': strings,
                                  'input_ports': array(ref('port')),
                                  'output_ports': array(ref('port')),
                                  'dependencies': strings,
                                  'decomposition_reason': text,
                                  'replaceability_statement': text})
    defs['connection'] = obj({**base, 'architecture_id': ident,
                              'from_module_id': ident, 'from_port_id': ident,
                              'to_module_id': ident, 'to_port_id': ident,
                              'contract_id': ident})
    defs['goal'] = obj({**base, 'purpose': text, 'in_scope': array(text, 1),
                        'out_of_scope': strings, 'success_criteria': array(text, 1),
                        'constraints': strings, 'sources': strings, 'replan_conditions': strings})
    defs['stage'] = obj({**base, 'goal_id': ident, 'purpose': text,
                         'dependencies': strings, 'entry_criteria': array(text, 1),
                         'exit_criteria': array(text, 1), 'module_checks': array(text, 1),
                         'integration_checks': array(text, 1),
                         'status': enum('planned', 'ready', 'active', 'ready_for_integration',
                                        'ready_for_stage_review', 'passed', 'invalidated', 'superseded')})
    defs['input'] = obj({'output_id': ident, 'revision': revision, 'fingerprint': text})
    defs['check_group'] = obj({'module_id': ident, 'purpose': text,
                               'boundary_required': {'type': 'boolean'},
                               'boundary_reason': string, 'check_ids': array(ident, 1)})
    defs['check'] = obj({'id': ident, 'module_ids': array(ident, 1),
                         'case': enum('normal', 'boundary', 'integration'), 'argv': array(text, 1),
                         'cwd': text, 'test_sources': array(text, 1), 'expected': text,
                         'timeout_seconds': {'type': 'number', 'minimum': 0.05},
                         'required': {'type': 'boolean'}, 'adapter': enum('unittest', 'junit', 'json')})
    defs['task'] = obj({**base, 'stage_id': ident, 'architecture_id': ident,
                        'architecture_revision': revision, 'module_ids': array(ident, 1),
                        'objective': text, 'exclusions': strings,
                        'context_refs': strings, 'current_state': text, 'gap': text,
                        'implementation_strategy': text, 'interface_contracts': array(text, 1),
                        'execution_steps': array(obj({'action': text, 'path': text,
                                                     'expected': text, 'verification': text}), 1),
                        'ownership': obj({'owned': array(text, 1), 'read_only': strings, 'forbidden': strings}),
                        'dependencies': strings, 'inputs': array(ref('input')),
                        'check_groups': array(ref('check_group'), 1), 'checks': array(ref('check'), 1),
                        'tested_paths': array(text, 1), 'acceptance_criteria': array(text, 1),
                        'failure_routes': array(text, 1), 'handoff': array(text, 1),
                        'unresolved': strings, 'self_check': text,
                        'status': enum('planned', 'ready', 'active', 'ready_for_review', 'passed',
                                       'failed', 'blocked', 'deferred', 'superseded'),
                        'input_validity': enum('current', 'stale', 'unknown'),
                        'adaptation_status': enum('pending', 'compatible', 'adapted',
                                                  'replan_required', 'blocked', 'obsolete')})
    defs['task']['properties']['check_source_hashes']={'type':'object','additionalProperties':text}
    defs['output'] = obj({**base, 'task_id': ident, 'module_id': ident,
                          'contract_ids': array(ident, 1), 'interface_key': text,
                          'contract': mapping, 'paths': array(text, 1), 'fingerprint': text,
                          'compatibility': enum('new', 'compatible', 'breaking')})
    defs['decision'] = obj({**base, 'text': text, 'source': text})
    defs['blocker'] = obj({**base, 'subject_id': ident, 'reason': text,
                           'resolved': {'type': 'boolean'}})
    defs['acceptance'] = obj({**base, 'subject_type': enum('task', 'stage', 'goal'),
                              'subject_id': ident, 'subject_revision': revision,
                              'result': enum('PASS', 'FAIL', 'BLOCKED'),
                              'review_mode': enum('self_review', 'independent'),
                              'reviewer': text, 'criteria': array(text, 1),
                              'evidence_ids': array(ident, 1), 'findings': string,
                              'supersedes': string})
    defs['record_ref'] = obj({'path': text, 'sha256': text})
    defs['evidence_ref'] = obj({'path':text,'sha256':text,'kind':enum('self_check','review'),
                                'subject_type':enum('task','stage','goal'),'subject_id':ident,
                                'subject_revision':revision,'status':enum('PASS','FAIL','BLOCKED','ERROR'),
                                'plan_id':text,'registered_revision':revision})
    maps = {name + 's': {'type': 'object', 'additionalProperties': ref(name)}
            for name in ('goal', 'architecture', 'contract', 'connection', 'stage', 'task',
                         'output', 'decision', 'blocker', 'acceptance')}
    maps['modules'] = {'type': 'object', 'additionalProperties': ref('product_module')}
    defs['state'] = obj({'schema_version': {'const': 2}, 'project_id': text, 'plan_id': text,
                         'retired_ids':array(ident),
                         'revision': {'type': 'integer', 'minimum': 0},
                         'status': enum('draft', 'awaiting_execution', 'executing', 'paused',
                                        'blocked', 'cancelled', 'completed'),
                         'entities': obj(maps),
                         'session': {'oneOf': [{'type': 'null'}, obj({'id': ident, 'owner': text})]},
                         'checkpoint': obj({'summary': string, 'next_steps': strings}),
                         'archive_index': {'type': 'object', 'additionalProperties': ref('record_ref')},
                         'evidence_index': {'type': 'object', 'additionalProperties': ref('evidence_ref')},
                         'receipts': {'type': 'object', 'additionalProperties': obj({'request_hash': text, 'response': mapping})}})
    defs['operation'] = obj({'schema_version': {'const': 2}, 'operation_id': ident,
                             'expected_revision': {'type': 'integer', 'minimum': 0},
                             'session_id': string,
                             'kind': enum('define_entity', 'revise_entity', 'archive_pending_plan',
                                          'claim_session', 'take_over_session', 'start_task',
                                          'save_checkpoint', 'submit_evidence', 'request_review',
                                          'record_acceptance', 'revise_contract', 'set_ready',
                                          'rebind_inputs', 'stage_review', 'pause', 'block',
                                          'cancel', 'complete', 'new_plan'), 'data': mapping})
    defs['test_case'] = obj({'id':text,'status':enum('PASS','FAIL','SKIP','BLOCKED'),'message':string},['id','status'])
    defs['assertion_report'] = obj({'tests':array(ref('test_case'))})
    defs['check_result'] = obj({'check_id':ident,'module_ids':array(ident,1),
                                'status':enum('PASS','FAIL','BLOCKED','ERROR'),
                                'returncode':{'oneOf':[{'type':'integer'},{'type':'null'}]},
                                'tests':array(ref('test_case')),'error':string,'report_path':text,'log_path':text})
    defs['self_check_result'] = obj({'schema_version':{'const':2},'kind':{'const':'self_check'},
                                     'task_id':ident,'task_revision':revision,'started_at':text,'finished_at':text,
                                     'binding':mapping,'status':enum('PASS','FAIL','BLOCKED','ERROR'),
                                     'exit_code':{'enum':[0,1,2,3]},
                                     'modules':array(obj({'module_id':ident,'status':enum('PASS','FAIL','BLOCKED','ERROR'),'check_ids':strings})),
                                     'checks':array(ref('check_result')),'attachments':array(ref('record_ref')),'error':string})
    defs['review_evidence'] = obj({'schema_version':{'const':2},'kind':{'const':'review'},'plan_id':text,
                                   'subject_type':enum('task','stage','goal'),'subject_id':ident,'subject_revision':revision,
                                   'subject_revisions':{'type':'object','additionalProperties':revision},
                                   'status':enum('PASS','FAIL','BLOCKED'),'criteria':array(text,1),
                                   'method':text,'expected':text,'actual':text,'reviewer':text,
                                   'review_mode':enum('self_review','independent'),
                                   'bindings':{'type':'object','additionalProperties':text},
                                   'attachments':array(ref('record_ref')),'supersedes':string})
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            '$id': 'https://planner-kernal.local/schema/v2', '$defs': defs,
            '$ref': '#/$defs/state'}
