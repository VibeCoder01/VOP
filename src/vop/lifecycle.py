"""Operator-only lifecycle requests, enabled by the local dashboard launcher."""
from uuid import uuid4

from fasthtml.components import A, P
from fasthtml.core import to_xml
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse, JSONResponse, Response


RESTART_JS = """document.addEventListener('submit', async event => {
  const form = event.target.closest('[data-vop-restart]');
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector('button');
  const message = form.querySelector('[role=status]');
  button.disabled = true;
  message.hidden = false;
  message.textContent = 'Restarting VOP. Waiting for the current observation to finish…';
  try {
    const response = await fetch(form.action, {method:'POST', body:new URLSearchParams(new FormData(form)), headers:{Accept:'application/json'}});
    if (!response.ok) throw new Error();
    const before = (await response.json()).instance_id;
    for (let attempt = 0; attempt < 180; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      try {
        const health = await fetch('/api/v1/health', {signal:AbortSignal.timeout(3000)});
        const state = health.ok ? await health.json() : null;
        if (state?.application === 'vop' && state.instance_id && state.instance_id !== before) {
          location.replace('/?notice=VOP+restarted.');
          return;
        }
      } catch (_) {}
    }
  } catch (_) {}
  message.textContent = 'VOP could not complete the restart. Open Start VOP to stop stale instances and start again.';
  button.disabled = false;
});"""


def install_lifecycle(app, store):
    app.state.instance_id = uuid4().hex
    app.state.shutdown_request = None

    @app.route('/ui/restart.js', methods=['GET'])
    def restart_script():
        return Response(RESTART_JS, media_type='application/javascript')

    async def control(request, mode):
        if request.scope.get('auth_role') != 'operator':
            return JSONResponse({'error': 'operator_required'}, status_code=403)
        callback = app.state.shutdown_request
        if callback is None:
            return JSONResponse({'error': 'Use Start VOP to enable restart controls.'}, status_code=409)
        store.audit('application_' + mode, 'requested')
        task = BackgroundTask(callback, mode)
        if mode == 'stop' or 'application/json' in request.headers.get('accept', ''):
            return JSONResponse({'status': mode + '_requested', 'instance_id': app.state.instance_id}, status_code=202, background=task)
        page = app.state.page('Restarting VOP', request, [
            P('VOP will finish the current observation, close its worker session and start again. Saved settings and monitoring are retained.'),
            P('Wait a moment, then return to the workspace.'), A('Return to VOP', href='/', cls='button')], view='settings')
        return HTMLResponse(to_xml(page), status_code=202, background=task)

    @app.route('/ui/restart', methods=['POST'])
    async def restart(request):
        return await control(request, 'restart')

    @app.route('/api/v1/shutdown', methods=['POST'])
    async def shutdown(request):
        return await control(request, 'stop')
