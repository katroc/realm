#!/usr/bin/python

import subprocess
import re
from ansible.module_utils.basic import AnsibleModule

def run_command(command, input_data=None):
    try:
        result = subprocess.run(command, input=input_data, text=True, capture_output=True, check=True)
        stdout = filter_password_prompts(result.stdout)
        stderr = result.stderr
        return stdout, stderr, result.returncode
    except subprocess.CalledProcessError as e:
        return filter_password_prompts(e.stdout), e.stderr, e.returncode

def filter_password_prompts(output):
    # Use a regex to filter out any line that starts with "Password for"
    # This is used to tidy stdout when running 'realm join'
    return re.sub(r'^Password for .+: $', '', output, flags=re.MULTILINE)

def parse_realm_details(realm_details_str):
    realm_details_dict = {}
    for line in realm_details_str.splitlines():
        parts = line.split(': ')
        if len(parts) == 2:
            key, value = parts
            key, value = key.strip(), value.strip()
            if value:
                if key in realm_details_dict:
                    if isinstance(realm_details_dict[key], list):
                        realm_details_dict[key].append(value)
                    else:
                        realm_details_dict[key] = [realm_details_dict[key], value]
                else:
                    realm_details_dict[key] = value
    return realm_details_dict

def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type='str', required=True),
            user=dict(type='str', required=True),
            password=dict(type='str', required=True, no_log=True),
            computer_ou=dict(type='str', required=False),
            manage_sssd=dict(type='bool', default=False),
            state=dict(type='str', choices=['present', 'absent'], default='present')
        ),
        supports_check_mode=True
    )

    domain = module.params['domain']
    user = module.params['user']
    password = module.params['password']
    computer_ou = module.params.get('computer_ou')
    manage_sssd = module.params['manage_sssd']
    state = module.params['state']

    if module.check_mode:
        module.exit_json(changed=True)

    if state == 'present':
        cmd = ['realm', 'join', '--user', user, domain]
        if computer_ou:
            cmd.extend(['--computer-ou', computer_ou])
        if manage_sssd:
            cmd.append('--automatic-id-mapping=no')

        stdout, stderr, rc = run_command(cmd, input_data=password)

        if rc != 0:
            if "Already joined to this domain" in stderr:
                module.exit_json(changed=False, msg=f"Host is already joined to {domain}", stdout=stdout, stderr="")
            else:
                module.fail_json(msg="Failed to join realm", stderr=stderr, stdout=stdout, rc=rc)

        realm_details_str, stderr, rc = run_command(['realm', 'list'])
        if rc != 0:
            module.fail_json(msg="Failed to retrieve realm details after join", stderr=stderr, stdout=realm_details_str, rc=rc)

        realm = parse_realm_details(realm_details_str)
        module.exit_json(changed=True, msg=f"Successfully joined {domain}", stdout=stdout, stderr=stderr, realm=realm)

    elif state == 'absent':
        cmd = ['realm', 'leave', domain]
        stdout, stderr, rc = run_command(cmd, input_data=password)

        if rc != 0:
            if "Not joined to this domain" in stderr:
                module.exit_json(changed=False, msg=f"Host is not joined to {domain}", stdout=stdout, stderr="")
            else:
                module.fail_json(msg="Failed to leave realm", stderr=stderr, stdout=stdout, rc=rc)

        module.exit_json(changed=True, msg=f"Successfully left {domain}", stdout=stdout, stderr=stderr)

if __name__ == '__main__':
    main()
