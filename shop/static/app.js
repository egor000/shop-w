const historyView = document.querySelector('#history');
const statusView = document.querySelector('#status');
const form = document.querySelector('#question-form');
const input = document.querySelector('#question');
const send = document.querySelector('#send');
const retry = document.querySelector('#retry');
let conversation;
let timer;
let busy = false;
let renderedQuestions = '';
let generation = 0;

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    const message = response.status === 404 ? 'This conversation is not available in this browser.'
      : response.status === 409 ? 'This question conflicts with an existing submission or a question already in progress.'
      : response.status === 422 ? 'Enter a question of 1–4,000 characters.'
      : 'Connection unavailable. Your submission is kept in this browser for retry.';
    throw new ApiError(response.status, message);
  }
  return response.json();
}

function outboxKey() { return `shop.outbox.${conversation}`; }
function setEnabled(enabled) { input.disabled = !enabled; send.disabled = !enabled; }

function renderHistory(questions) {
  const serialized = JSON.stringify(questions);
  if (serialized === renderedQuestions) {
    return;
  }
  renderedQuestions = serialized;
  historyView.replaceChildren();
  for (const question of questions) {
    const article = document.createElement('article');
    const heading = document.createElement('h2');
    heading.textContent = 'You asked';
    const text = document.createElement('p');
    text.textContent = question.text;
    article.append(heading, text);
    if (question.answer) {
      const answer = document.createElement('p');
      answer.textContent = question.answer.text;
      article.append(answer);
      for (const product of question.answer.products) {
        const link = document.createElement('a');
        link.textContent = `View ${product.name}`;
        link.href = product.url;
        article.append(link);
      }
    }
    historyView.append(article);
  }
}

function render(questions) {
  renderHistory(questions);
  const latest = questions.at(-1);
  const pending = latest && ['waiting', 'processing'].includes(latest.status);
  statusView.textContent = pending ? (latest.status === 'waiting' ? 'Waiting for an answer…' : 'Preparing your answer…')
    : latest?.status === 'completed' ? 'Answer saved.'
    : latest?.status === 'expired' ? 'The question expired before an answer was ready. You can ask again.'
    : latest?.status === 'failed' ? 'The answer could not be prepared. You can ask again.' : 'Ready for your question.';
  setEnabled(!pending && !localStorage.getItem(outboxKey()));
}

function showError(error) {
  setEnabled(false);
  statusView.textContent = error instanceof ApiError ? error.message : 'Connection unavailable. Reconnect to recover your conversation and retry any unsent question.';
  retry.hidden = false;
}

async function refresh() {
  clearTimeout(timer);
  const started = generation;
  try {
    const state = await api(`/api/conversations/${conversation}`);
    if (started !== generation) return;
    render(state.questions);
    retry.hidden = true;
    timer = setTimeout(refresh, 1000);
  } catch (error) {
    if (started === generation) showError(error);
  }
}

async function flushOutbox() {
  const saved = localStorage.getItem(outboxKey());
  if (!saved) return;
  const submission = JSON.parse(saved);
  try {
    await api(`/api/conversations/${conversation}/questions`, submission);
    localStorage.removeItem(outboxKey());
    input.value = '';
  } catch (error) {
    if (error instanceof ApiError && [409, 422].includes(error.status)) {
      // A definitive rejection is safe to edit; uncertain delivery retains the ID.
      localStorage.removeItem(outboxKey());
      input.value = submission.text;
    }
    throw error;
  }
}

async function connect() {
  if (busy) return;
  busy = true;
  generation += 1;
  clearTimeout(timer);
  retry.hidden = true;
  try {
    await api('/api/session', {});
    conversation = new URL(location.href).searchParams.get('conversation') || localStorage.getItem('shop.conversation');
    if (!conversation) {
      conversation = (await api('/api/conversations', {})).id;
      localStorage.setItem('shop.conversation', conversation);
    }
    const url = new URL(location.href);
    url.searchParams.set('conversation', conversation);
    window.history.replaceState(null, '', url);
    await flushOutbox();
    await refresh();
  } catch (error) { showError(error); }
  finally { busy = false; }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !input.value.trim()) return;
  busy = true;
  generation += 1;
  clearTimeout(timer);
  setEnabled(false);
  statusView.textContent = 'Sending your question…';
  try {
    // Persist both text and identity before the first network attempt.
    localStorage.setItem(outboxKey(), JSON.stringify({ submission_id: crypto.randomUUID(), text: input.value }));
    await flushOutbox();
    await refresh();
  } catch (error) { showError(error); }
  finally { busy = false; }
});
retry.addEventListener('click', connect);
connect();
