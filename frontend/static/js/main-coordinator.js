/* MAIN_KOORD: programs, atomic JSON import, dispatch, measures, live risks. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id), E=Api.el;
  const ROUTE='/api/program-routing';
  let programs=[], measures={}, sections=[], departments={}, dispatch={}, staged=[], currentProgram='', currentSection='';
  let flagPanel=null, reportPanel=null, editingMeasureId=null, editingRiskId=null, riskReturnToMeasure=false;
  const riskCache=new Map();
  let activeView="programs";
  // Статистика за призначеними виконавцями: тільки дані із захищеного API.
  const progressCache = new Map();
  const progressLoading = new Set();
  const progressPeriod = () => $('mc-progress-period')?.value || Api.currentPeriod();
  const progressKey = (programId) => programId + '|' + progressPeriod();

  function requestProgress(programId) {
    const key = progressKey(programId);
    if (progressCache.has(key) || progressLoading.has(key)) return;
    progressLoading.add(key);
    Api.get(ROUTE + '/programs/' + encodeURIComponent(programId)
      + '/progress?period=' + encodeURIComponent(progressPeriod()))
      .then(data => progressCache.set(key, {data}))
      .catch(err => progressCache.set(key, {error: err.message || 'Помилка отримання прогресу'}))
      .finally(() => {
        progressLoading.delete(key);
        if (activeView === 'programs') render();
      });
  }

  function progressStats(item) {
    const n = Number(item.assigned || 0);
    const a = Number(item.approved || 0);
    const part = make('div', {class: 'mc-progress-stats'});
    part.appendChild(make('strong', {text: 'Погоджено ' + a + ' із ' + n}));
    const extras = [];
    if (item.pending) extras.push('Очікують: ' + item.pending);
    if (item.rejected) extras.push('Відхилено: ' + item.rejected);
    if (item.not_submitted) extras.push('Не подано: ' + item.not_submitted);
    part.appendChild(make('span', {class: 'small muted', text: extras.join(' · ') || (n ? 'Усі подання погоджені' : 'Призначень немає')}));
    const track = make('div', {class: 'mc-progress-track', role: 'progressbar',
      'aria-label': 'Погоджені подання', 'aria-valuemin': '0',
      'aria-valuemax': String(n), 'aria-valuenow': String(a)});
    track.appendChild(make('span', {class: 'mc-progress-fill'}));
    track.firstChild.style.width = (n ? Math.min(100, 100 * a / n) : 0) + '%';
    part.appendChild(track);
    return part;
  }

  function renderProgramProgress(body, programId) {
    requestProgress(programId);
    const progress = progressCache.get(progressKey(programId));
    const wrap = make('section', {class: 'mc-dept-progress', 'aria-label': 'Прогрес за підрозділами'});
    wrap.appendChild(make('h3', {text: 'Прогрес за підрозділами · ' + Api.periodLabel(progressPeriod())}));
    if (!progress) {
      wrap.appendChild(make('p', {class: 'small muted', text: 'Завантаження стану виконання…'}));
    } else if (progress.error) {
      wrap.appendChild(make('p', {class: 'small mc-progress-error', text: 'Не вдалося отримати прогрес: ' + progress.error}));
    } else if (!progress.data.departments?.length) {
      wrap.appendChild(make('p', {class: 'small muted', text: 'Програму ще не направлено підрозділам.'}));
    } else {
      const list = make('div', {class: 'mc-dept-progress-list'});
      progress.data.departments.forEach(d => {
        const row = make('div', {class: 'mc-dept-progress-row'});
        row.appendChild(make('div', {class: 'mc-dept-progress-name'}, [
          make('strong', {text: d.department_name || d.department_id}),
          make('span', {class: 'small muted', text: 'Заходів із призначеннями: ' + d.measures_total
            + ' / ' + progress.data.measures_total}),
        ]));
        row.appendChild(progressStats(d));
        list.appendChild(row);
      });
      wrap.appendChild(list);
      if (progress.data.unassigned_measures) wrap.appendChild(make('p', {
        class: 'small muted mc-progress-footnote',
        text: 'Заходів без призначених виконавців: ' + progress.data.unassigned_measures,
      }));
    }
    body.appendChild(wrap);
  }

  function renderMeasureProgress(details, programId, measureId) {
    const progress = progressCache.get(progressKey(programId));
    if (!progress || progress.error || !progress.data) return;
    const depts = (progress.data.departments || []).map(d => ({
      department: d,
      measure: (d.measures || []).find(row => row.measure_id === measureId),
    })).filter(row => row.measure);
    const wrap = make('div', {class: 'mc-measure-progress'});
    wrap.appendChild(make('strong', {text: 'Виконання за підрозділами'}));
    if (!depts.length) {
      wrap.appendChild(make('p', {class: 'small muted', text: 'Виконавців ще не призначено.'}));
    } else {
      depts.forEach(({department, measure}) => {
        const row = make('div', {class: 'mc-measure-progress-row'});
        row.appendChild(make('span', {text: department.department_name || department.department_id}));
        row.appendChild(progressStats(measure));
        wrap.appendChild(row);
      });
    }
    details.appendChild(wrap);
  }

  const expanded = new Set(); // Попередня деревоподібна навігація
  const make=(tag,attributes,children)=>E(tag,attributes,children);
  const views=['programs','catalog','risk','reports'];
  async function activateView(view) {
    if (!views.includes(view)) return;
    activeView=view;
    for (const name of views) {
      const panel=$('mc-view-'+name);
      const tab=$('mc-tab-'+name);
      if(panel)panel.hidden=name!==view;
      if(tab){
        tab.classList.toggle('active',name===view);
        tab.setAttribute('aria-selected',String(name===view));
        tab.tabIndex=name===view?0:-1;
      }
    }
    await refreshActivePanel();
  }
  // Завантажуємо лише відкритий розділ; недоступність Risk Flags/звітів
  // не блокує дерево програм та роботу з ними.
  async function refreshActivePanel() {
    if(activeView==='catalog'){
      await refreshRiskCatalog();
    }else if(activeView==='risk' && $('mc-risk-panel') && window.RiskFlagPanel?.mount){
      try{
        if(!flagPanel)flagPanel=RiskFlagPanel.mount('mc-risk-panel',()=>programs,
          ()=>$('mc-risk-period')?.value||Api.currentPeriod(),focusMeasure);
        if(flagPanel)await flagPanel.refresh();
      }catch(err){$('mc-risk-panel').textContent='Не вдалося завантажити Risk Flags: '+err.message;}
    }else if(activeView==='reports' && $('mc-report-panel') && window.ReportPanel?.mount){
      try{
        if(!reportPanel)reportPanel=ReportPanel.mount('mc-report-panel',()=>programs,
          ()=>$('mc-report-period')?.value||Api.currentPeriod());
        if(reportPanel)await reportPanel.refresh();
      }catch(err){$('mc-report-panel').textContent='Не вдалося завантажити звіти: '+err.message;}
    }
  }
  const show=(id)=>$(id)&&$(id).showModal();
  const close=(id)=>$(id)&&$(id).close();
  const hidden=(id,yes)=>$(id)&&$(id).classList.toggle('hidden',yes);
  const error=(id,msg)=>{ if(!$(id))return;$(id).textContent=msg||'';$(id).classList.toggle('hidden',!msg); };
  const toast=(msg,err)=>{
    const stack=$('mc-toasts'); if(!stack)return;
    const n=make('div',{class:'role-message '+(err?'error':'success'),text:msg});stack.prepend(n);setTimeout(()=>n.remove(),7000);
  };
  const types={date:'Дата',ongoing:'Постійний',recurring:'Періодичний'};
  function setSelect(sel,items,current){
    sel.replaceChildren();items.forEach(x=>sel.appendChild(make('option',{value:x.id,text:x.name})));
    if(current)sel.value=current;
  }
  // Основні дані мають завантажуватися незалежно від допоміжних панелей.
  async function list() {
    Api.showError(null);
    progressCache.clear(); // Оновлюємо після змін призначень та погоджень.
    const mine = await Api.get(ROUTE + '/my/programs');
    const owners = (mine || []).filter(p => p.access_type === 'owner');

    const data = await Promise.all(owners.map(async function (p) {
      const id = encodeURIComponent(p.id);
      const [program, full, available, sent] = await Promise.all([
        Api.get(ROUTE + '/programs/' + id),
        Api.measures(p.id),
        Api.optional(Api.get(ROUTE + '/programs/' + id + '/available-departments')),
        Api.optional(Api.get(ROUTE + '/programs/' + id + '/dispatches')),
      ]);
      measures[p.id] = Array.isArray(full) ? full : [];
      departments[p.id] = Array.isArray(available.data) ? available.data : [];
      dispatch[p.id] = (Array.isArray(sent.data) ? sent.data : []).map(x => x.department_id);
      return program;
    }));
    programs = data;
    Object.values(departments).flat().forEach(d => {
      if (d.id && d.name) Api.DEPARTMENTS[d.id] = d.name;
    });

    // Основний шлях — довідник розділів MAIN_KOORD. Якщо його endpoint
    // недоступний, беремо розділи тільки з програм, які дозволено бачити.
    const catalog = await Api.optional(Api.get('/api/sections/'));
    sections = Array.isArray(catalog.data) ? catalog.data : [];
    if (!sections.length && programs.length) {
      const sectionsOfPrograms = await Promise.all(programs.map(p =>
        Api.optional(Api.get(ROUTE + '/programs/' + encodeURIComponent(p.id) + '/sections'))
      ));
      const seen = new Set();
      sectionsOfPrograms.forEach(result => (result.data || []).forEach(s => {
        if (!seen.has(s.id)) { seen.add(s.id); sections.push(s); }
      }));
    }
    if (!sections.length) sections = [
      {id: 'R1', number: 1, title: 'Організаційні заходи'},
      {id: 'R2', number: 2, title: 'Заходи запобігання корупції'},
      {id: 'R3', number: 3, title: 'Контроль і моніторинг'},
    ];
    sections.sort((a,b) => Number(a.number) - Number(b.number));

    for(const id of ['mc-risk-period','mc-report-period','mc-progress-period']){
      const select=$(id);
      if(!select)continue;
      const previous=select.value;
      Api.fillPeriods(select,programs);
      if(previous && [...select.options].some(o=>o.value===previous))select.value=previous;
    }
    render();
    fillProgramSelectors();
    await refreshActivePanel();
  }

  function focusMeasure(id){
    const select=$('mc-search');if(select)select.value=id;
    activateView('programs').then(()=>{render();$('mc-programs')?.scrollIntoView({behavior:'smooth',block:'start'});});
  }
  function state(p){return (measures[p.id]||[]).length;}
  function render(){
    $('mc-count-programs').textContent=programs.length;
    $('mc-count-measures').textContent=programs.reduce((sum,p)=>sum+state(p),0);
    $('mc-count-dispatched').textContent=programs.filter(p=>(dispatch[p.id]||[]).length).length;
    // KPI: захід вважається виконаним, тільки якщо всі його призначені
    // виконавці мають погоджені актуальні подання за вибраний період.
    // Зведення по підрозділах об'єднуємо за measure_id, не подвоюючи заходи.
    let completed=0, waiting=false, unavailable=false;
    for(const program of programs){
      requestProgress(program.id);
      const progress=progressCache.get(progressKey(program.id));
      if(!progress){ waiting=true; continue; }
      if(progress.error || !progress.data){ unavailable=true; continue; }
      const byMeasure=new Map();
      (progress.data.departments||[]).forEach(department=>{
        (department.measures||[]).forEach(row=>{
          const current=byMeasure.get(row.measure_id)||{assigned:0,approved:0};
          current.assigned+=Number(row.assigned||0);
          current.approved+=Number(row.approved||0);
          byMeasure.set(row.measure_id,current);
        });
      });
      completed += [...byMeasure.values()].filter(row=>row.assigned>0&&row.assigned===row.approved).length;
    }
    $('mc-count-completed').textContent=unavailable?'—':waiting?'…':completed;
    const q=$('mc-search').value.toLowerCase(),filter=$('mc-filter').value;
      const host=$('mc-programs');host.replaceChildren();let shown=0;
      const autoExpand=!!q||filter!=='all';
      const toggle=(key)=>{expanded.has(key)?expanded.delete(key):expanded.add(key);render();};
      const button=(children,opened)=>make('button',{class:'row-head',type:'button','aria-expanded':String(opened)},children);
      const action=(target,label,callback,variant='btn')=>{
        const b=make('button',{type:'button',class:variant,text:label});
        b.addEventListener('click',callback);target.appendChild(b);
      };
      programs.forEach(function(p){
        const items=measures[p.id]||[];
        if(filter==='empty'&&items.length)return;
        if(filter==='draft'&&(dispatch[p.id]||[]).length)return;
        if(filter==='sent'&&!(dispatch[p.id]||[]).length)return;
        if(q&&!(p.title+' '+p.id+' '+(p.organization_name||'')+' '+items.map(m=>m.description+' '+m.id+' '+m.section_id).join(' ')).toLowerCase().includes(q))return;
        shown++;
        const pkey='p:'+p.id,popen=autoExpand||expanded.has(pkey);
        const card=make('section',{class:'prog',id:'mc-program-'+p.id});
        const header=button([
          make('span',{class:'title'},[
            make('span',{class:'code',text:p.id}),
            make('span',{text:p.title||p.id}),
            make('span',{class:'sub',text:p.organization_name||''}),
          ]),
          make('span',{class:'meta',text:Api.fmtDate(p.start_date)+' – '+Api.fmtDate(p.end_date)}),
          make('span',{class:'count',text:items.length+' заходів'}),
        ],popen);
        header.addEventListener('click',()=>toggle(pkey));card.appendChild(header);
        if(popen){
          const body=make('div',{class:'prog-body'});
          const bar=make('div',{class:'prog-tools'});
          bar.appendChild(make('div',{class:'small muted',text:(p.approval_reference||'')+((dispatch[p.id]||[]).length?' · Направлено '+dispatch[p.id].length+' підрозділам':' · Ще не направлено')}));
          const acts=make('div',{class:'mc-legacy-actions'});
          action(acts,'Направити підрозділам',()=>openDispatch(p.id));
          action(acts,'Додати захід',()=>openMeasure(p.id));
          action(acts,'Редагувати програму',()=>openEdit(p));
          action(acts,'Видалити',()=>deleteProgram(p));
          bar.appendChild(acts);body.appendChild(bar);
          renderProgramProgress(body, p.id);
          const bySection={};items.forEach(m=>(bySection[m.section_id]||(bySection[m.section_id]=[])).push(m));
          Object.keys(bySection).sort(Api.compareSections).forEach(sid=>{
            const rows=bySection[sid],sec=sections.find(x=>x.id===sid),sk='s:'+p.id+':'+sid,sopen=autoExpand||expanded.has(sk);
            const section=make('section',{class:'sec'});
            const dates=rows.map(x=>x.deadline_on).filter(Boolean).sort();
            const sectionHeader=button([
              make('span',{class:'title',text:(sec?sec.number+'. '+sec.title:sid)}),
              make('span',{class:'meta',text:dates.length?'До '+Api.fmtDate(dates[dates.length-1]):'Постійно / періодично'}),
              make('span',{class:'count',text:rows.length+' заходів'}),
            ],sopen);
            sectionHeader.addEventListener('click',()=>toggle(sk));section.appendChild(sectionHeader);
            if(sopen){
              const inner=make('div',{class:'sec-body'});
              rows.sort(Api.byMeasureOrder).forEach(m=>{
                const mk='m:'+m.id,mopen=autoExpand||expanded.has(mk);
                const node=make('div',{class:'measure',id:'mc-measure-'+m.id});
                const mheader=button([
                  make('span',{class:'num',text:Api.measureNo(m)}),
                  make('span',{text:m.description}),
                  make('span',{class:'meta',text:Api.fmtDate(m.deadline_on)||m.deadline_description||'—'}),
                  make('span',{class:'chip',text:'План'}),
                ],mopen);
                mheader.addEventListener('click',()=>toggle(mk));node.appendChild(mheader);
                if(mopen){
                  const details=make('div',{class:'detail mc-legacy-detail'});
                  renderMeasureProgress(details, p.id, m.id);
                  const tools=make('div',{class:'mc-legacy-actions mc-measure-actions'});
                  action(tools,'Редагувати захід',()=>openEditMeasure(m));
                  action(tools,'Видалити захід',()=>deleteMeasure(m));
                  details.appendChild(tools);node.appendChild(details);
                }
                inner.appendChild(node);
              });section.appendChild(inner);
            }
            body.appendChild(section);
          });
          if(!items.length)body.appendChild(make('div',{class:'coord-empty',text:'Поки немає заходів. Натисніть «Додати захід».'}));
          card.appendChild(body);
        }
        host.appendChild(card);
      });
      if(!shown)host.appendChild(make('div',{class:'role-empty',text:'Програм немає або вони не відповідають пошуку.'}));
      $('mc-list-caption').textContent='Програм: '+shown;
    }
  function readForm(form){const data=Object.fromEntries(new FormData(form));delete data.file;return data;}
  function programFields(form){
    const f=readForm(form);f.has_restricted_information=!!form.elements.has_restricted_information?.checked;
    f.coordinator_department_id=Api.me.department_id||null;
    f.approval_status='draft'; // Статус прихований в інтерфейсі, але обов'язковий для імпорту.
    f.notes=f.notes||'';return f;
  }
  function measureFields(form){
    const f=readForm(form);
    f.sequence_number=Number(f.sequence_number);
    f.deadline_on=f.deadline_type==='date'?(f.deadline_on||null):null;
    f.risk_id=f.risk_id||null;f.assigned_user_id=null;
    f.indicator_target=f.indicator_target?Number(f.indicator_target):null;
    f.indicator_unit=f.indicator_unit||null;
    // Відповідальний підрозділ визначає бекенд з профілю MAIN_KOORD.
    // Для атомарного імпорту чернетки це поле ще потрібне в JSON-схемі.
    f.responsible_department_id=Api.me.department_id||null;
    f.collaborator_department_ids=[];
    return f;
  }
  function drawStaged(){
    const host=$('mc-draft-sections');host.replaceChildren();
    sections.forEach(section=>{
      const box=make('section',{class:'role-card'});
      box.appendChild(make('h3',{text:section.number+'. '+section.title}));
      staged.filter(m=>m.section_id===section.id).forEach(m=>{
        const line=make('div',{class:'d-flex justify-content-between align-items-start gap-2 border-bottom py-2'});
        line.appendChild(make('span',{text:m.sequence_number+'. '+m.description}));
        const remove=make('button',{type:'button',class:'btn btn-sm btn-outline-danger',text:'Прибрати'});
        remove.addEventListener('click',()=>{staged=staged.filter(x=>x!==m);drawStaged();});
        line.appendChild(remove);box.appendChild(line);
      });
      const add=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:'+ Захід'});
      add.addEventListener('click',()=>openMeasure(null,section.id));box.appendChild(add);host.appendChild(box);
    });
    $('mc-draft-count').textContent=staged.length;
  }
  function stage(step){hidden('mc-step-1',step!==1);hidden('mc-step-2',step!==2);hidden('mc-next',step!==1);hidden('mc-back',step!==2);hidden('mc-submit',step!==2);
    $('mc-builder').dataset.step=String(step);drawStaged();}
  function openBuilder(){staged=[];$('mc-program-form').reset();stage(1);error('mc-builder-error','');show('mc-builder');}
  function sectionNumber(){
    const section=sections.find(item=>item.id===currentSection);
    return section?.number || currentSection;
  }
  function duplicateSequence(){
    const form=$('mc-measure-form');
    const raw=form.elements.sequence_number.value;
    const number=Number(raw);
    if(!raw || !Number.isInteger(number) || number<1)return false;
    const rows=currentProgram?(measures[currentProgram]||[]):staged;
    return rows.some(item=>item.section_id===currentSection
      && Number(item.sequence_number)===number && item.id!==editingMeasureId);
  }
  function validateSequence(){
    const form=$('mc-measure-form');
    const input=form.elements.sequence_number;
    const duplicate=duplicateSequence();
    const message=duplicate?'Номер '+input.value+' уже існує у розділі '+sectionNumber()+'. Виберіть інший.':'';
    input.setCustomValidity(message);
    const hint=$('mc-measure-sequence-hint');
    hint.textContent=message||'Номер має бути унікальним у розділі '+sectionNumber()+' цієї програми.';
    hint.classList.toggle('text-danger',duplicate);
    return !duplicate;
  }
  function resetSequence(){
    const form=$('mc-measure-form');
    form.elements.sequence_number.setCustomValidity('');
    $('mc-measure-sequence-label').textContent='Номер у розділі '+sectionNumber();
  }
  function openMeasure(programId,sectionId){
    editingMeasureId=null;
    $('mc-measure-form').elements.id.readOnly=false;
    currentProgram=programId||'';currentSection=sectionId||sections[0]?.id||'R1';
    $('mc-measure-form').reset();resetSequence();
    $('mc-measure-title').textContent=programId?'Новий захід для програми '+programId:'Додати захід до чернетки';
    const existing=(programId?(measures[programId]||[]):staged)
      .filter(item=>item.section_id===currentSection);
    const occupied=new Set(existing.map(item=>Number(item.sequence_number)));
    let next=1;while(occupied.has(next))next++;
    $('mc-measure-form').elements.sequence_number.value=next;
    validateSequence();
    hidden('mc-deadline-date-row',false);
    error('mc-measure-error','');show('mc-measure-dialog');
    prepareMeasureRisks(programId||'').catch(err=>error('mc-measure-error',err.message));
  }
  function openEditMeasure(m){
    editingMeasureId=m.id;currentProgram=m.program_id;currentSection=m.section_id;
    const form=$('mc-measure-form');form.reset();resetSequence();
    ['id','sequence_number','description','deadline_type','deadline_on',
      'deadline_description','completion_indicator','indicator_target','indicator_unit','required_evidence',
      'resources','risk_id'].forEach(k=>{if(form.elements[k])form.elements[k].value=m[k]??'';});
    form.elements.id.readOnly=true;
    validateSequence();
    prepareMeasureRisks(m.program_id||'',m.risk_id||'').catch(err=>error('mc-measure-error',err.message));
    hidden('mc-deadline-date-row',m.deadline_type!=='date');
    $('mc-measure-title').textContent='Редагування заходу '+m.id;
    error('mc-measure-error','');show('mc-measure-dialog');
  }
  async function submitMeasure(event){event.preventDefault();error('mc-measure-error','');
    if(!validateMeasureRiskChoice())return;
    const form=event.currentTarget;const f=measureFields(form);f.section_id=currentSection;
    if(currentProgram){f.program_id=currentProgram;delete f.collaborator_department_ids;}
    else { f.section_id=currentSection; }
    try{
      validateSequence();
      if(!form.reportValidity())return;
      if(editingMeasureId){
        delete f.id;delete f.assigned_user_id;delete f.collaborator_department_ids;
        // Під час редагування зберігаємо наявний відповідальний підрозділ.
        delete f.responsible_department_id;
        await Api.patch('/api/measures/'+encodeURIComponent(editingMeasureId),f);
        toast('Захід оновлено');await list();
      }
      else if(currentProgram){await Api.post('/api/measures/',f);toast('Захід створено');await list();}
      else{
        if(staged.some(m=>m.id===f.id))throw new Error('Такий ID вже є в чернетці');
        if(duplicateSequence())throw new Error('Такий номер заходу вже існує в цьому розділі');
        staged.push(f);drawStaged();toast('Захід додано до чернетки');
      }
      close('mc-measure-dialog');
    }catch(err){error('mc-measure-error',err.message);}
  }
  async function submitProgram(event){event.preventDefault();error('mc-builder-error','');
    if($('mc-builder').dataset.step!=='2'){stage(2);return;}
    if(!staged.length)return error('mc-builder-error','Додай хоча б один захід.');
    const p=programFields(event.currentTarget);
    const payload={program:p,sections:sections.map(s=>({id:s.id,number:s.number,title:s.title,measures:staged.filter(m=>m.section_id===s.id).map(m=>{
      const {section_id,program_id,...v}=m;return v;
    })}))};
    const file=new File([JSON.stringify(payload)],'program.json',{type:'application/json'});
    const fd=new FormData();fd.set('file',file);
    try{await Api.post('/api/program-import/',fd);close('mc-builder');toast('Програму та заходи створено однією транзакцією');await list();}
    catch(err){error('mc-builder-error',err.message);}
  }
  function openEdit(p){currentProgram=p.id;const f=$('mc-edit-program-form');f.reset();
    ['title','organization_name','start_date','end_date','approval_reference','goals','notes'].forEach(k=>f.elements[k].value=p[k]||'');
    $('mc-edit-title').textContent='Редагувати '+p.id;error('mc-edit-error','');show('mc-edit-program-dialog');}
  async function saveEdit(ev){ev.preventDefault();const data=readForm(ev.currentTarget);
    try{await Api.patch('/api/programs/'+encodeURIComponent(currentProgram),data);close('mc-edit-program-dialog');toast('Зміни збережено');await list();}
    catch(err){error('mc-edit-error',err.message);}
  }
  async function deleteMeasure(m){if(!confirm('Видалити захід '+m.id+'?'))return;
    try{await Api.del('/api/measures/'+encodeURIComponent(m.id));toast('Захід видалено');await list();}catch(err){toast(err.message,true);}}
  async function deleteProgram(p){if(!confirm('Видалити всю програму '+p.id+'? Дію не можна скасувати.'))return;
    try{await Api.del('/api/programs/'+encodeURIComponent(p.id));toast('Програму видалено');await list();}catch(err){toast(err.message,true);}}
  async function openDispatch(id){currentProgram=id;const q=encodeURIComponent(id);
    error('mc-dispatch-error','');
    try{
      const rows=await Api.get(ROUTE+'/programs/'+q+'/available-departments');
      const box=$('mc-dept-list');box.replaceChildren();
      (rows||[]).forEach(d=>{Api.DEPARTMENTS[d.id]=d.name;
        const label=make('label',{class:'d-block py-2'},[make('input',{type:'checkbox',value:d.id,name:'departments',class:'me-2'}),make('span',{text:d.name+' ('+d.id+')'})]);box.appendChild(label);
      });
      if(!rows.length)box.appendChild(make('p',{class:'role-empty',text:'Немає доступних підрозділів із координатором.'}));
      show('mc-dispatch-dialog');
    }catch(err){toast(err.message,true);}
  }
  async function submitDispatch(ev){ev.preventDefault();const ids=[...$('mc-dept-list').querySelectorAll('input:checked')].map(x=>x.value);
    if(!ids.length)return error('mc-dispatch-error','Оберіть хоча б один підрозділ.');
    try{await Api.post(ROUTE+'/programs/'+encodeURIComponent(currentProgram)+'/departments',{department_ids:ids});
      close('mc-dispatch-dialog');toast('Програму направлено');await list();}
    catch(err){error('mc-dispatch-error',err.message);}
  }
  async function importFile(ev){ev.preventDefault();const file=$('mc-json-file').files[0];if(!file)return;
    const fd=new FormData();fd.set('file',file);
    try{await Api.post('/api/program-import/',fd);close('mc-import-dialog');toast('JSON імпортовано');await list();}
    catch(err){error('mc-import-error',err.message);}
  }

  // === Незалежний реєстр ризиків підрозділу ===
  function fillProgramSelectors(){
    // Від програми реєстр ризиків більше не залежить.
    if($('mc-risk-create'))$('mc-risk-create').disabled=false;
  }
  async function risksOf(_programId='',force=false){
    const key='department';
    if(!force&&riskCache.has(key))return riskCache.get(key);
    const data=await Api.getAll('/api/risks/',100,'skip');
    const rows=Array.isArray(data)?data:[];
    riskCache.set(key,rows);
    return rows;
  }
  const riskLevels={low:'Низький',medium:'Середній',high:'Високий',critical:'Критичний'};
  function riskLabel(r){return r.id+' — '+r.title+' · '+(riskLevels[r.level]||r.level);}
  // Єдине поле пошуку та вибору ризику у формі заходу (тільки MAIN_KOORD).
  const measureRiskPicker={rows:[],visible:[],active:-1,loading:false,requestId:0};
  const riskNorm=s=>String(s||'').toLocaleLowerCase('uk-UA').trim();
  function closeMeasureRiskOptions(){
    const input=$('mc-measure-risk-input'),list=$('mc-measure-risk-options');
    if(!input||!list)return;
    list.hidden=true;
    input.setAttribute('aria-expanded','false');
    input.removeAttribute('aria-activedescendant');
    measureRiskPicker.active=-1;
  }
  function chooseMeasureRisk(risk){
    const input=$('mc-measure-risk-input'),hidden=$('mc-measure-risk-value');
    hidden.value=risk?.id||'';
    input.value=risk?.id?riskLabel(risk):'';
    input.setCustomValidity('');
    $('mc-measure-risk-hint').textContent=risk?.id?'Обрано: '+risk.id:'Без прив’язки до ризику.';
    closeMeasureRiskOptions();
  }
  function showMeasureRiskOptions(showAll=false){
    const input=$('mc-measure-risk-input'),list=$('mc-measure-risk-options');
    if(measureRiskPicker.loading || input.disabled)return;
    const selected=measureRiskPicker.rows.find(r=>r.id===$('mc-measure-risk-value').value);
    const query=showAll||(selected&&input.value===riskLabel(selected))?'':riskNorm(input.value);
    const results=measureRiskPicker.rows.filter(r=>
      !query||riskNorm(r.id+' '+r.title+' '+(r.process_name||'')).includes(query));
    // При пошуку першим іде релевантний ризик; за порожнього пошуку — «без прив’язки».
    measureRiskPicker.visible=query?[...results,null]:[null,...results];
    measureRiskPicker.active=-1;
    list.replaceChildren();
    measureRiskPicker.visible.forEach((risk,index)=>{
      const item=make('button',{
        id:'mc-measure-risk-option-'+index,type:'button',role:'option',
        class:'mc-risk-combo-option','aria-selected':'false',
        text:risk?riskLabel(risk):'Без прив’язки до ризику',
      });
      item.addEventListener('mousedown',e=>e.preventDefault());
      item.addEventListener('click',()=>chooseMeasureRisk(risk));
      list.appendChild(item);
    });
    if(query&&!results.length)list.prepend(make('div',{class:'mc-risk-combo-empty',text:'Ризиків за запитом немає'}));
    list.hidden=false;
    input.setAttribute('aria-expanded','true');
  }
  function highlightMeasureRiskOption(){
    const input=$('mc-measure-risk-input');
    $('mc-measure-risk-options').querySelectorAll('.mc-risk-combo-option').forEach((item,index)=>{
      const active=index===measureRiskPicker.active;
      item.classList.toggle('is-active',active);
      item.setAttribute('aria-selected',String(active));
      if(active){
        input.setAttribute('aria-activedescendant',item.id);
        item.scrollIntoView({block:'nearest'});
      }
    });
  }
  async function prepareMeasureRisks(_programId='',selectedId=''){
    const requestId=++measureRiskPicker.requestId;
    const input=$('mc-measure-risk-input'),hidden=$('mc-measure-risk-value');
    const hint=$('mc-measure-risk-hint'),toggle=$('mc-measure-risk-toggle');
    measureRiskPicker.rows=[];measureRiskPicker.visible=[];
    measureRiskPicker.loading=true;
    input.value='';hidden.value=selectedId||'';
    input.setCustomValidity('');input.disabled=true;toggle.disabled=true;
    closeMeasureRiskOptions();
    hint.textContent='Завантаження ризиків…';
    try{
      const risks=await risksOf();
      if(requestId!==measureRiskPicker.requestId)return;
      measureRiskPicker.rows=risks;
      const risk=risks.find(r=>r.id===selectedId);
      if(risk){input.value=riskLabel(risk);hidden.value=risk.id;}
      else if(selectedId){
        input.value=selectedId+' (ризик відсутній у відповіді API)';
        hidden.value=selectedId; // Не скидаємо стару прив'язку під час редагування.
      }
      hint.textContent=selectedId&&!risk?'Попередній ризик не знайдено в отриманому реєстрі.':
        risks.length?'Доступно ризиків: '+risks.length+'. Шукайте за кодом або назвою.':
          'Ризиків у відповіді API немає.';
    }finally{
      if(requestId===measureRiskPicker.requestId){
        measureRiskPicker.loading=false;input.disabled=false;toggle.disabled=false;
      }
    }
  }
  function validateMeasureRiskChoice(){
    const input=$('mc-measure-risk-input'),hidden=$('mc-measure-risk-value');
    if(measureRiskPicker.loading){
      error('mc-measure-error','Триває завантаження ризиків.');return false;
    }
    if(input.value.trim()&&!hidden.value){
      input.setCustomValidity('Оберіть ризик із випадаючого списку або очистьте поле.');
      input.reportValidity();return false;
    }
    input.setCustomValidity('');return true;
  }
  // Реальні маршрути з backend/app/api/risk_assessments.py.
  // Роутер має бути підключений під /api в app.main.
  const reassessmentAPI = {
    getRisk: id => {
      const cached = riskCache.get('department')?.find(r => String(r.id) === String(id));
      return cached ? Promise.resolve(cached) : risksOf('', true).then(rows => {
        const found = rows.find(r => String(r.id) === String(id));
        if (!found) throw new Error('Ризик ' + id + ' відсутній у реєстрі');
        return found;
      });
    },
    getHistory: id => Api.get('/api/risk-assessments/' + encodeURIComponent(id) + '/history'),
    getTrend: id => Api.get('/api/risk-assessments/' + encodeURIComponent(id) + '/trend'),
    createAssessment: (id, data) => Api.post('/api/risk-assessments/' + encodeURIComponent(id) + '/drafts', data),
    approve: (id, assessmentId, reason) => Api.post('/api/risk-assessments/' + encodeURIComponent(id) + '/drafts/' + encodeURIComponent(assessmentId) + '/approve', {reason}),
    reject: (id, assessmentId, reason) => Api.post('/api/risk-assessments/' + encodeURIComponent(id) + '/drafts/' + encodeURIComponent(assessmentId) + '/reject', {reason}),
    baseline: id => Api.post('/api/risk-assessments/' + encodeURIComponent(id) + '/baseline', {}),
    registerMeasurement: (id, data) => Api.post('/api/risk-assessments/' + encodeURIComponent(id) + '/measurements', data),
  };
  let reassessmentRequest = 0;
  async function openRiskReassessment(risk) {
    const dialog = $('mc-reassessment-dialog');
    const host = $('mc-reassessment-host');
    if (!dialog || !host) return;
    const request = ++reassessmentRequest;
    host.replaceChildren();
    $('mc-reassessment-title').textContent = 'Повторне оцінювання · ' + risk.id;
    if (!dialog.open) dialog.showModal();
    if (typeof window.mountRiskReassessment !== 'function') {
      host.textContent = 'Не завантажено /static/js/risk-reassessment.js';
      return;
    }
    try {
      await window.mountRiskReassessment({
        container: host,
        riskId: risk.id,
        api: reassessmentAPI,
        onSaved: async () => {
          riskCache.clear();
          if (activeView === 'catalog') await refreshRiskCatalog(true);
        },
      });
      if (request !== reassessmentRequest || !dialog.open) host.replaceChildren();
    } catch (err) {
      host.textContent = 'Не вдалося відкрити оцінювання: ' + (err.message || err);
    }
  }

  async function refreshRiskCatalog(force=false){
    const host=$('mc-risk-catalog-list'), message=$('mc-risk-catalog-message');
    if(!host||!message)return;
    host.replaceChildren(); message.textContent='Завантаження ризиків…';
    try{
      const risks=await risksOf('',force);
      const q=($('mc-risk-search')?.value||'').trim().toLocaleLowerCase('uk');
      const filtered=risks.filter(r=>(r.id+' '+r.title+' '+r.process_name)
        .toLocaleLowerCase('uk').includes(q));
      message.textContent='Знайдено: '+filtered.length+' із '+risks.length;
      if(!filtered.length){host.appendChild(make('div',{
        class:'role-empty',text:'Ризиків за цим пошуком немає.'}));return;}
      filtered.forEach(r=>{
        const card=make('article',{class:'mc-risk-record'});
        const head=make('div',{class:'mc-risk-record-head'});
        head.appendChild(make('strong',{text:r.id+' · '+r.title}));
        const actions=make('div',{class:'mc-risk-record-actions'});
        const edit=make('button',{type:'button',class:'btn',text:'Редагувати'});
         edit.addEventListener('click',()=>openRiskDialog('',r));actions.appendChild(edit);
         const reassess=make('button',{type:'button',class:'btn btn-dark',text:'Повторно оцінити'});
         reassess.addEventListener('click',()=>openRiskReassessment(r));actions.appendChild(reassess);
        const del=make('button',{type:'button',class:'btn',text:'Видалити'});
        del.addEventListener('click',()=>deleteRisk(r));actions.appendChild(del);
        head.appendChild(actions);card.appendChild(head);
        card.appendChild(make('p',{text:r.description}));
        card.appendChild(make('div',{class:'mc-risk-meta',text:'Процес: '+r.process_name
          +' · Рівень: '+(riskLevels[r.level]||r.level)
          +' · Бал: '+r.score+' · Ціль: '+Api.fmtDate(r.target_date)}));
        host.appendChild(card);
      });
    }catch(err){message.textContent='Не вдалося отримати ризики: '+err.message;}
  }
  function updateRiskScore(){
    const f=$('mc-risk-form');if(!f)return;
    const a=Number(f.elements.probability_score.value),b=Number(f.elements.impact_score.value);
    f.elements.score.value=a*b;
  }
  function openRiskDialog(_programId='',risk=null,returnToMeasure=false){
    const form=$('mc-risk-form');
    editingRiskId=risk?.id||null; riskReturnToMeasure=returnToMeasure;
    form.reset(); form.elements.id.readOnly=!!risk;
    if(risk){
      for(const [key,value] of Object.entries(risk)){
        if(form.elements[key])form.elements[key].value=value??'';
      }
    }
    $('mc-risk-dialog-title').textContent=risk?'Редагування ризику '+risk.id:'Створити корупційний ризик';
    $('mc-risk-save').textContent=risk?'Зберегти зміни':'Створити ризик';
    updateRiskScore();error('mc-risk-form-error','');show('mc-risk-dialog');
  }
  async function submitRisk(event){
    event.preventDefault();const form=event.currentTarget;
    if(!form.reportValidity())return;
    error('mc-risk-form-error','');
    const payload=readForm(form);
    payload.probability_score=Number(payload.probability_score);
    payload.impact_score=Number(payload.impact_score);
    payload.score=payload.probability_score*payload.impact_score;
    payload.indicator_baseline_value=Number(payload.indicator_baseline_value);
    payload.indicator_target_value=Number(payload.indicator_target_value);
    const editing=!!editingRiskId;
    if(editing)delete payload.id;
    try{
      const saved=editing
        ?await Api.patch('/api/risks/'+encodeURIComponent(editingRiskId),payload)
        :await Api.post('/api/risks/',payload);
      riskCache.clear();
      close('mc-risk-dialog');toast(editing?'Ризик оновлено':'Ризик створено');
      if(riskReturnToMeasure&&$('mc-measure-dialog')?.open)
        await prepareMeasureRisks(currentProgram,saved.id);
      if(activeView==='catalog')await refreshRiskCatalog();
    }catch(err){error('mc-risk-form-error',err.message);}
  }
  async function deleteRisk(risk){
    if(!confirm('Видалити ризик '+risk.id+'? Пов’язані із заходами ризики видалити неможливо.'))return;
    try{
      await Api.del('/api/risks/'+encodeURIComponent(risk.id));
      riskCache.clear();toast('Ризик видалено');await refreshRiskCatalog();
    }catch(err){toast(err.message,true);}
  }

  async function init(){if(!await Api.requireRole('MAIN_KOORD'))return;
    for(const id of ['mc-risk-period','mc-report-period','mc-progress-period']){
      const select=$(id);
      if(select){Api.fillPeriods(select,[]);select.addEventListener('change',refreshActivePanel);}
    }
    document.querySelectorAll('[data-mc-view]').forEach(tab=>{
      tab.addEventListener('click',()=>activateView(tab.dataset.mcView));
      tab.addEventListener('keydown',event=>{
        if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;
        event.preventDefault();
        const current=views.indexOf(tab.dataset.mcView);
        const next=event.key==='Home'?0:event.key==='End'?views.length-1:
          (current+(event.key==='ArrowRight'?1:-1)+views.length)%views.length;
        $('mc-tab-'+views[next])?.focus();activateView(views[next]);
      });
    });
    $('mc-search').addEventListener('input',render);$('mc-filter').addEventListener('change',render);
    $('mc-progress-period').addEventListener('change', render);
    $('mc-risk-search').addEventListener('input',()=>refreshRiskCatalog());
    $('mc-risk-reload').addEventListener('click',()=>refreshRiskCatalog(true));
    $('mc-risk-create').addEventListener('click',()=>openRiskDialog());
    // Введення та вибір в одному пошуковому списку.
    $('mc-measure-risk-input').addEventListener('input',()=>{
      $('mc-measure-risk-value').value='';
      $('mc-measure-risk-input').setCustomValidity('');
      showMeasureRiskOptions();
    });
    $('mc-measure-risk-input').addEventListener('focus',()=>showMeasureRiskOptions());
    $('mc-measure-risk-toggle').addEventListener('click',()=>{
      const isClosed=$('mc-measure-risk-options').hidden;
      if(isClosed){$('mc-measure-risk-input').focus();showMeasureRiskOptions(true);}
      else closeMeasureRiskOptions();
    });
    $('mc-measure-risk-input').addEventListener('keydown',event=>{
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();
        if($('mc-measure-risk-options').hidden)showMeasureRiskOptions();
        const count=measureRiskPicker.visible.length;
        if(count){
          measureRiskPicker.active=(measureRiskPicker.active+(event.key==='ArrowDown'?1:-1)+count)%count;
          highlightMeasureRiskOption();
        }
      }else if(event.key==='Enter'){
        event.preventDefault();
        if(!$('mc-measure-risk-options').hidden && measureRiskPicker.visible.length){
          chooseMeasureRisk(measureRiskPicker.visible[Math.max(0,measureRiskPicker.active)]);
        }
      }else if(event.key==='Escape'&&!$('mc-measure-risk-options').hidden){
        event.preventDefault();event.stopPropagation();closeMeasureRiskOptions();
      }
    });
    document.addEventListener('pointerdown',event=>{
      if(!$('mc-measure-risk-combo').contains(event.target))closeMeasureRiskOptions();
    });
    $('mc-measure-risk-combo').addEventListener('focusout',()=>setTimeout(()=>{
      if(!$('mc-measure-risk-combo').contains(document.activeElement))closeMeasureRiskOptions();
    },0));
    $('mc-measure-form').elements.sequence_number.addEventListener('input',validateSequence);
    $('mc-risk-form').elements.probability_score.addEventListener('change',updateRiskScore);
    $('mc-risk-form').elements.impact_score.addEventListener('change',updateRiskScore);
    $('mc-risk-form').addEventListener('submit',submitRisk);
    $('mc-reload').addEventListener('click',()=>list().catch(Api.showError));
    $('mc-create').addEventListener('click',openBuilder);
    $('mc-import-open').addEventListener('click',()=>{error('mc-import-error','');show('mc-import-dialog');});
    document.querySelectorAll('[data-dialog-close]').forEach(b=>b.addEventListener('click',()=>close(b.dataset.dialogClose)));
    $('mc-next').addEventListener('click',()=>{if($('mc-program-form').reportValidity())stage(2);});
    $('mc-back').addEventListener('click',()=>stage(1));
    document.querySelectorAll('#mc-builder [data-step]').forEach(b=>b.addEventListener('click',()=>{
      const n=Number(b.dataset.step);if(n===1||$('mc-program-form').reportValidity())stage(n);
    }));
    $('mc-program-form').addEventListener('submit',submitProgram);
    $('mc-measure-form').addEventListener('submit',submitMeasure);
    $('mc-edit-program-form').addEventListener('submit',saveEdit);
    $('mc-dispatch-form').addEventListener('submit',submitDispatch);
    $('mc-import-form').addEventListener('submit',importFile);
    $('mc-dept-search').addEventListener('input',ev=>{
      const q=ev.target.value.toLowerCase();[...$('mc-dept-list').children].forEach(item=>item.hidden=!item.textContent.toLowerCase().includes(q));
    });
    $('mc-json-file').addEventListener('change',ev=>{$('mc-json-preview').textContent=ev.target.files[0]?.name||'Файл не вибрано';});
    $('mc-measure-form').elements.deadline_type.addEventListener('change',ev=>hidden('mc-deadline-date-row',ev.target.value!=='date'));
    try{await list();}catch(err){Api.showError(err);}
  }
  init();
})();
