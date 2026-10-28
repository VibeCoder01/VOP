"""No browser, credentials or network: exercise the shared fetch guard."""
import json
import shutil
import subprocess

import pytest

from vop.dashboard import WORKSPACE_JS


@pytest.mark.skipif(not shutil.which('node'), reason='Node required for JavaScript contract')
def test_expired_session_stops_network_preserves_page_and_blocks_form_submit():
    harness = r"""
const assert = require('node:assert/strict');
global.window=global;
global.location={href:'http://127.0.0.1:8765/',origin:'http://127.0.0.1:8765'};
let calls=0, warnings=[], submit;
global.fetch=async()=>{calls++; return new Response('',{status:401});};
global.document={
 createElement:()=>({setAttribute(){}}),
 querySelector:()=>({prepend:warning=>warnings.push(warning)}),
 addEventListener:(name,handler)=>{assert.equal(name,'submit');submit=handler;}
};
eval(SOURCE);
(async()=>{
 assert.equal((await fetch('/api/v1/health')).status,401);
 assert.equal(calls,1); assert.equal(warnings.length,1);
 for(let i=0;i<30;i++) assert.equal((await fetch('/ui/camera-answers/test')).status,401);
 assert.equal(calls,1); assert.equal(warnings.length,1);
 assert.match(warnings[0].textContent,/Open Start VOP/);
 assert.match(warnings[0].textContent,/Unsaved changes/);
 let prevented=false; submit({preventDefault(){prevented=true;}});
 assert(prevented);
 await fetch('https://example.test/'); assert.equal(calls,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('SOURCE', json.dumps(WORKSPACE_JS))
    result = subprocess.run([shutil.which('node'), '-e', harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
