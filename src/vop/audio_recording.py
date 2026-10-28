"""Browser-only microphone capture and conversion; the existing save route stores PCM WAV."""
from fasthtml.components import Audio, Button, Div, Input, Label, P, Script


def audio_editor(saved=False):
    return Div(
        Label('Choose an audio file', _for='audio-file'),
        Input(type='file', accept='audio/*,.mp3,.m4a,.wav,.ogg,.flac,.webm', id='audio-file', data_audio_upload=''),
        Input(type='hidden', name='audio_data'),
        P('MP3, M4A, WAV or another format supported by your browser. Maximum 00:01:00 and 10 MB. Audio is converted automatically.', cls='muted'),
        Label('Or record a clip'),
        Div(Button('Start recording', type='button', disabled=True, data_record_start=''),
            Button('Stop recording', type='button', disabled=True, data_record_stop=''),
            Button('Cancel recording', type='button', hidden=True, data_record_cancel=''),
            Button('Discard clip', type='button', hidden=True, data_audio_discard=''), cls='actions', role='group', aria_label='Microphone recording controls'),
        P('Select Start recording to use this computer’s microphone. Nothing is saved until you select Save action.',
          data_audio_status='', role='status', aria_live='polite', cls='muted'),
        Audio(controls=True, preload='metadata', hidden=True, data_audio_preview='', aria_label='Preview the selected audio clip'),
        P('Leave the audio unchanged to keep the saved clip.' if saved else 'Record a clip or choose a file before saving.', cls='muted'),
        P('JavaScript is needed to record or import audio.', cls='muted'),
        Script(src='/ui/audio-editor.js', defer=True), data_audio_editor='', data_saved='yes' if saved else 'no', cls='field')


SCRIPT = r"""(() => {
  const editor = document.querySelector('[data-audio-editor]');
  if (!editor) return;
  const find = name => editor.querySelector('[data-' + name + ']');
  const upload = find('audio-upload'), start = find('record-start'), stop = find('record-stop');
  const cancel = find('record-cancel'), discard = find('audio-discard');
  const preview = find('audio-preview'), status = find('audio-status');
  const data = editor.querySelector('[name=audio_data]'), form = editor.closest('form');
  const Decoder = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const canRecord = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder && Decoder);
  const submit = [...form.querySelectorAll('button:not([type]),button[type=submit]')];
  let generation = 0, busy = false, recorder, stream, limit, ticker, previewURL;
  let previousDisabled = submit.map(button => button.disabled), mode = 'idle';
  const time = seconds => '00:' + String(Math.floor(seconds / 60)).padStart(2,'0') + ':' + String(Math.floor(seconds % 60)).padStart(2,'0');
  function release() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    clearTimeout(limit); clearInterval(ticker);
  }
  function state(next) {
    mode = next; const wasBusy = busy; busy = next !== 'idle';
    if (busy && !wasBusy) previousDisabled = submit.map(button => button.disabled);
    submit.forEach((button,i) => { button.disabled = busy ? true : previousDisabled[i]; });
    upload.disabled = busy; start.disabled = busy || !canRecord;
    stop.disabled = next !== 'recording'; cancel.hidden = !busy;
    cancel.textContent = next === 'asking' ? 'Cancel microphone request' : 'Cancel';
    discard.hidden = busy || !data.value;
    preview.hidden = busy || !previewURL;
  }
  function clearPreview() {
    preview.pause(); preview.removeAttribute('src'); preview.load();
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null; preview.hidden = true;
  }
  function selected(bytes, message) {
    let binary = '';
    for (let i=0; i<bytes.length; i+=16384) binary += String.fromCharCode(...bytes.subarray(i,i+16384));
    data.value = btoa(binary); upload.value = ''; upload.setCustomValidity('');
    clearPreview(); previewURL = URL.createObjectURL(new Blob([bytes],{type:'audio/wav'}));
    preview.src = previewURL; status.textContent = message + ' Play it below, then select Save action.';
  }
  function wav(buffer, truncate) {
    if (!buffer.length || !Number.isFinite(buffer.duration) || (!truncate && buffer.duration > 60))
      throw new Error('Choose an audio clip no longer than 00:01:00.');
    const frames = Math.min(buffer.length, 60 * 16000);
    const bytes = new Uint8Array(44 + frames * 2), view = new DataView(bytes.buffer);
    const label = (at,value) => [...value].forEach((c,i) => view.setUint8(at+i,c.charCodeAt(0)));
    label(0,'RIFF'); view.setUint32(4,bytes.length-8,true); label(8,'WAVE'); label(12,'fmt ');
    view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
    view.setUint32(24,16000,true); view.setUint32(28,32000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
    label(36,'data'); view.setUint32(40,frames*2,true);
    const channels = Array.from({length:buffer.numberOfChannels},(_,i) => buffer.getChannelData(i));
    for (let i=0; i<frames; i++) {
      let sample=0; for (const channel of channels) sample += channel[i] / channels.length;
      sample = Math.max(-1,Math.min(1,sample));
      view.setInt16(44+i*2,Math.round(sample*(sample<0?32768:32767)),true);
    }
    return bytes;
  }
  async function convert(blob, truncate=false) {
    if (!Decoder) throw new Error('This browser cannot import audio. Use a current browser such as Edge or Chrome.');
    let buffer;
    try { buffer = await new Decoder(1,1,16000).decodeAudioData(await blob.arrayBuffer()); }
    catch (_) { throw new Error('This browser could not read the clip. Try an MP3, M4A or WAV file.'); }
    return wav(buffer,truncate);
  }
  function durationOf(file) {
    // Read metadata before decoding, so an accidentally selected long song is not expanded in memory.
    return new Promise((resolve,reject) => {
      const probe = document.createElement('audio'), url = URL.createObjectURL(file);
      const finish = error => {
        clearTimeout(timeout); probe.onloadedmetadata = probe.onerror = null;
        probe.removeAttribute('src'); probe.load(); URL.revokeObjectURL(url);
        error ? reject(new Error(error)) : resolve();
      };
      const timeout = setTimeout(() => finish('The clip could not be read. Try an MP3, M4A or WAV file.'),10000);
      probe.onloadedmetadata = () => finish(!Number.isFinite(probe.duration) || probe.duration <= 0 ?
        'The clip’s length could not be read. Try an MP3, M4A or WAV file.' : probe.duration > 60 ?
        'Choose an audio clip no longer than 00:01:00.' : '');
      probe.onerror = () => finish('This browser could not read the clip. Try an MP3, M4A or WAV file.');
      probe.preload = 'metadata'; probe.src = url;
    });
  }
  function cancelWork(message='Cancelled. Your previous audio is unchanged.') {
    generation++; release();
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    recorder = null; upload.value=''; state('idle'); status.textContent = message;
  }
  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    release(); stop.disabled=true;
  }
  upload.addEventListener('change', async () => {
    const file = upload.files[0]; if (!file || busy) return;
    const mine = ++generation; preview.pause(); state('importing');
    status.textContent = 'Preparing the audio clip…';
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Choose an audio file smaller than 10 MB.');
      await durationOf(file); if (mine !== generation) return;
      const bytes = await convert(file); if (mine !== generation) return;
      selected(bytes,'Audio clip ready.');
    } catch (error) { if (mine === generation) status.textContent = error.message + ' Your previous audio is unchanged.'; }
    finally { if (mine === generation) { upload.value=''; state('idle'); } }
  });
  start.addEventListener('click', async () => {
    if (busy || !canRecord) return;
    const mine = ++generation; preview.pause(); state('asking');
    status.textContent = 'Allow microphone access in your browser, or select Cancel.';
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1},video:false});
      if (mine !== generation) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream = acquired;
      const chunks=[]; let size=0, failure='';
      recorder = new MediaRecorder(stream, {audioBitsPerSecond:64000});
      const current = recorder;
      current.ondataavailable = event => {
        if (mine !== generation || !event.data.size) return;
        size += event.data.size;
        if (size > 8 * 1024 * 1024) { failure='The recording was too large. Try a shorter clip.'; if (current.state !== 'inactive') current.stop(); release(); }
        else chunks.push(event.data);
      };
      current.onerror = () => { if (mine !== generation) return; failure='Recording failed. Check the microphone, then try again or choose an audio file.'; release(); if (current.state !== 'inactive') current.stop(); };
      current.onstop = async () => {
        if (mine !== generation) return;
        release(); recorder=null; state('converting'); status.textContent='Preparing your recording…';
        try {
          if (failure) throw new Error(failure);
          const bytes = await convert(new Blob(chunks,{type:current.mimeType}),true);
          if (mine === generation) selected(bytes,'Recording ready.');
        } catch (error) { if (mine === generation) status.textContent=error.message + ' Your previous audio is unchanged.'; }
        finally { if (mine === generation) state('idle'); }
      };
      current.start(250); state('recording');
      const began=performance.now();
      const update = () => { status.textContent='Recording ' + time(Math.min(60,(performance.now()-began)/1000)) + ' / 00:01:00'; };
      update(); ticker=setInterval(update,1000);
      limit=setTimeout(() => { if (mine === generation) stopRecording(); },60000);
    } catch (error) {
      if (mine !== generation) return;
      release(); state('idle');
      status.textContent = error.name === 'NotAllowedError' ? 'Microphone access was not allowed. Allow it in your browser and try again, or choose an audio file.' :
        error.name === 'NotFoundError' ? 'No microphone was found. Connect one and try again, or choose an audio file.' :
        'The microphone could not be opened. Check that another app is not using it, then try again or choose an audio file.';
    }
  });
  stop.addEventListener('click', () => { if (mode === 'recording') stopRecording(); });
  cancel.addEventListener('click', () => cancelWork());
  discard.addEventListener('click', () => {
    if (busy) return;
    generation++; data.value=''; upload.value=''; upload.setCustomValidity(''); clearPreview(); state('idle');
    status.textContent = editor.dataset.saved === 'yes' ? 'Clip discarded. The saved audio will be kept.' : 'Clip discarded. Record again or choose an audio file.';
  });
  form.addEventListener('submit', event => { if (busy) { event.preventDefault(); status.textContent='Stop recording or wait for the clip to finish preparing before saving.'; } });
  document.addEventListener('visibilitychange', () => { if (document.hidden && mode === 'recording') stopRecording(); });
  window.addEventListener('pagehide', () => { cancelWork(); clearPreview(); });
  state('idle');
  if (!canRecord) status.textContent='Microphone recording is not available in this browser. Use a current browser at localhost, or choose an audio file.';
})();"""
