const csrf = document.querySelector('meta[name=csrf]')?.content;
const role = document.querySelector('#role')?.dataset.role;
const actions = {
  patient: {Booked:['Cancelled'],Confirmed:['Cancelled']},
  assistant: {Booked:['Confirmed','Cancelled'],Confirmed:['Waiting','Cancelled']},
  doctor: {Waiting:['In consultation'],'In consultation':['Completed']},
  admin: {Booked:['Confirmed','Cancelled'],Confirmed:['Waiting','Cancelled'],Waiting:['In consultation'],'In consultation':['Completed']}
};
let appointments = [];
const active = ['Booked','Confirmed','Waiting','In consultation'];
const now = () => new Date().toLocaleString('sv-SE').replace(' ','T').slice(0,16);
const readable = date => date.replace('T',' · ');

function fillSlots(slots) {
  const select = document.querySelector('#slots');
  if (!select) return;
  select.replaceChildren(new Option(slots.length ? 'Choose a time' : 'No available slots', ''));
  const calendar = document.querySelector('#calendar');
  calendar.replaceChildren();
  for (const slot of slots) {
    select.add(new Option(slot.name + ' · ' + readable(slot.start), slot.id));
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary slot-button';
    button.textContent = readable(slot.start);
    button.onclick = () => {
      select.value = slot.id;
      document.querySelectorAll('.slot-button').forEach(b => b.classList.remove('selected'));
      button.classList.add('selected');
    };
    calendar.append(button);
  }
  document.querySelector('#booking').scrollIntoView({behavior:'smooth',block:'center'});
}
document.querySelectorAll('.choose').forEach(button => button.onclick = async () => {
  try {
    const response = await fetch('/api/slots?doctor=' + button.dataset.doctor);
    if (!response.ok) throw Error('Unable to load availability.');
    document.querySelector('#selected-doctor').textContent = 'Dr. ' + button.dataset.name;
    fillSlots(await response.json());
  } catch (error) { document.querySelector('#selected-doctor').textContent = error.message; }
});
document.querySelectorAll('.prompt-suggestion').forEach(button => button.onclick = () => {
  document.querySelector('#prompt').value = button.dataset.prompt;
});
document.querySelector('#smart')?.addEventListener('submit', async event => {
  event.preventDefault();
  const output = document.querySelector('#smart-result');
  output.textContent = 'Finding available times…';
  try {
    const response = await fetch('/api/smart', {
      method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({text:document.querySelector('#prompt').value})
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    output.textContent = data.matches.length + ' matching times. Choose one below.';
    fillSlots(data.matches);
  } catch (error) { output.textContent = error.message; }
});

function filteredRows() {
  const view = document.querySelector('#appointment-view').value;
  const status = document.querySelector('#status-filter').value;
  const doctor = document.querySelector('#doctor-filter').value;
  const date = document.querySelector('#date-filter').value;
  return appointments.filter(a => {
    if (view === 'upcoming' && (!active.includes(a.status) || a.start < now())) return false;
    if (view === 'history' && active.includes(a.status) && a.start >= now()) return false;
    if (status !== 'all' && a.status !== status) return false;
    if (doctor !== 'all' && String(a.doctor_id) !== doctor) return false;
    if (date && !a.start.startsWith(date)) return false;
    return true;
  });
}
function hidden(form, name, value) {
  const input = document.createElement('input');
  input.type='hidden';input.name=name;input.value=value;form.append(input);
}
function statusButton(a, next) {
  const form=document.createElement('form');
  form.method='post';form.action='/appointment/'+a.id+'/status';
  hidden(form,'csrf',csrf);hidden(form,'status',next);
  const button=document.createElement('button');
  button.textContent=next;button.className='secondary small-button';
  if (next==='Cancelled') button.onclick=e => {
    if (!confirm('Cancel this appointment?')) e.preventDefault();
  };
  form.append(button);
  return form;
}
async function reschedule(a) {
  try {
    const response=await fetch('/api/slots?doctor='+a.doctor_id);
    if (!response.ok) throw Error('Unable to load open times.');
    const slots=await response.json();
    if (!slots.length) { alert('No alternative slots available.'); return; }
    const choice=prompt('Choose a new time by number:\n'+slots.map((s,i)=>(i+1)+'. '+readable(s.start)).join('\n'));
    if (choice===null) return;
    const number=Number(choice);
    if (!Number.isInteger(number) || number<1 || number>slots.length) {alert('Invalid choice.');return;}
    if (!confirm('Confirm new appointment time: '+readable(slots[number-1].start)+'?'))return;
    const form=document.createElement('form');
    form.method='post';form.action='/appointment/'+a.id+'/reschedule';
    hidden(form,'csrf',csrf);hidden(form,'slot',slots[number-1].id);
    document.body.append(form);form.submit();
  } catch (error) {alert(error.message);}
}
function renderAppointments() {
  const tbody=document.querySelector('#appointments');
  tbody.replaceChildren();
  const rows=filteredRows();
  if (!rows.length) {
    const tr=tbody.insertRow();const td=tr.insertCell();td.colSpan=5;
    td.textContent='No appointments match your filters.';return;
  }
  for (const a of rows) {
    const tr=tbody.insertRow();
    for (const value of [readable(a.start),a.doctor,a.patient,a.status]) {
      const td=tr.insertCell();td.textContent=value;
      if(value===a.status) td.className='status status-'+a.status.toLowerCase().replaceAll(' ','-');
    }
    const cell=tr.insertCell();cell.className='action-cell';
    for (const next of actions[role][a.status] || []) cell.append(statusButton(a,next));
    if (['patient','assistant','admin'].includes(role) && ['Booked','Confirmed'].includes(a.status) && a.start >= now()) {
      const button=document.createElement('button');button.textContent='Reschedule';
      button.className='secondary small-button';button.onclick=()=>reschedule(a);cell.append(button);
    }
    if (!cell.children.length) cell.textContent='—';
  }
}
function updateStats() {
  const ongoing=appointments.filter(a=>active.includes(a.status));
  let numbers;
  if (role==='patient') numbers=[
    ongoing.filter(a=>a.start>=now()).length,
    appointments.filter(a=>a.status==='Completed').length,
    appointments.filter(a=>a.status==='Cancelled').length
  ];
  else if (role==='doctor') numbers=[
    ongoing.filter(a=>a.start.startsWith(now().slice(0,10))).length,
    appointments.filter(a=>a.status==='Waiting').length,
    appointments.filter(a=>a.status==='Completed').length
  ];
  else numbers=[
    ongoing.length,
    appointments.filter(a=>a.status==='Waiting').length,
    appointments.filter(a=>a.status==='Completed').length
  ];
  document.querySelectorAll('[data-stat]').forEach((el,i)=>el.textContent=numbers[i]);
}
async function refresh() {
  try {
    const response=await fetch('/api/appointments');
    if (!response.ok) throw Error();
    appointments=await response.json();renderAppointments();updateStats();
  } catch(error) {console.warn('Unable to refresh appointments.');}
}
if (role) {
  refresh();setInterval(refresh,8000);
  document.querySelector('#refresh').onclick=refresh;
  document.querySelectorAll('#appointment-view,#status-filter,#doctor-filter,#date-filter')
    .forEach(el=>el.addEventListener('change',renderAppointments));
}
