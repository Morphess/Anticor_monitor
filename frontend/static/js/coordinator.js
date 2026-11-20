/* KOORD: one scoped dashboard with assignments, approvals, SHA alerts and RF. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id),E=Api.el,route='/api/program-routing';
  const make=(tag,a,ch)=>E(tag,a,ch);
  let programs=[],byProgram={},measures=[],executions={},assignments={},alerts=[],selectedFilter='all',flagsPanel,reportPanel;
  const expanded = new Set(); // Старе дерево: програма → розділ → захід
  const notice=(text,isError)=>{ const box=$('coord-toast');if(!box)return;
    $('coord-toast-message').textContent=text;box.classList.remove('hidden');box.dataset.kind=isError?'error':'success';setTimeout(()=>box.classList.add('hidden'),6500);
  };
  const fail=err=>{Api.showError(err);notice(err.message||String(err),true);};
  const submissions=m=>executions[m.id]||[];
  const assigned=m=>assignments[m.id]||[];
  const ownSubmission=(m,userId)=>submissions(m).find(e=>Number(e.submitted_by_user_id)===Number(userId));
  const pending=m=>submissions(m).some(e=>e.status==='pending'&&!e.document_changed);
  const approved=m=>assigned(m).length>0&&assigned(m).every(a=>{
    const e=ownSubmission(m,a.user_id);
    return e&&e.status==='approved'&&!e.document_changed;
  });
  const isOverdue=m=>m.deadline_on&&m.deadline_on<Api.today()&&!approved(m);
  const pendingCount=()=>measures.reduce((n,m)=>n+submissions(m).filter(e=>e.status==='pending'&&!e.document_changed).length,0);
  const approvedCount=m=>assigned(m).filter(a=>{const e=ownSubmission(m,a.user_id);return e&&e.status==='approved'&&!e.document_changed;}).length;
  const statusLabel=m=>{
    if(approved(m))return 'Погоджено';
    if(pending(m))return 'Очікує рішення';
    if(!submissions(m).length)return assigned(m).length?'Не подано':'Не призначено';
    const n=approvedCount(m),total=assigned(m).length;
    return total ? ('Погоджено '+n+' / '+total) : 'Не призначено';
  };
  function render(){
    $('coord-total').textContent=measures.length;
    $('coord-program-total').textContent=programs.length+' програм';
    $('coord-approved').textContent=measures.filter(approved).length;
    $('coord-review-count').textContent=pendingCount();
    $('coord-overdue').textContent=measures.filter(isOverdue).length;
    ['all','approved','review','overdue','unassigned'].forEach(f=>{
      const n=$('coord-filter-'+f);if(n)n.textContent=measures.filter(m=>f==='all'||(f==='approved'&&approved(m))||(f==='review'&&pending(m))||(f==='overdue'&&isOverdue(m))||(f==='unassigned'&&!(assignments[m.id]||[]).length)).length;
    });
    $('coord-unassigned-filter').classList.remove('hidden');
    document.querySelectorAll('[data-coord-filter]').forEach(b=>{const active=b.dataset.coordFilter===selectedFilter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    const search=$('search').value.trim().toLowerCase();const period=$('period').value;
    const items=measures.filter(m=>{
      if(selectedFilter==='approved'&&!approved(m))return false;
      if(selectedFilter==='review'&&!pending(m))return false;
      if(selectedFilter==='overdue'&&!isOverdue(m))return false;
      if(selectedFilter==='unassigned'&&(assignments[m.id]||[]).length)return false;
      return !search||[m.id,m.description,m.program_id,Api.deptName(m.responsible_department_id),submissions(m).map(e=>e.order_number).join(' ')].join(' ').toLowerCase().includes(search);
    });
    $('coord-results-caption').textContent='Показано '+items.length+' із '+measures.length+' заходів';
    $('coord-section-title').textContent='Заходи підрозділу';
      const host=$('programs'); host.replaceChildren();
      const inspectMode=!!search || selectedFilter!=='all';
      if(!items.length){
        host.appendChild(make('div',{class:'coord-empty'},[
          make('strong',{text:'Заходів не знайдено'}),
          make('span',{text:'Змініть пошук або фільтр, щоб переглянути доступні заходи.'}),
        ]));return;
      }
      const byPid={};items.forEach(m=>(byPid[m.program_id]||(byPid[m.program_id]=[])).push(m));
      const toggle=(key)=>{expanded.has(key)?expanded.delete(key):expanded.add(key);render();};
      const head=(text,details)=>make('button',{type:'button',class:'row-head','aria-expanded':String(details)},text);
      Object.entries(byPid).forEach(([pid,all])=>{
        const p=byProgram[pid]||{}, key='p:'+pid;
        const showProgram=inspectMode||expanded.has(key);
        const card=make('section',{class:'prog','aria-label':'Програма '+pid});
        const heading=head([
          make('span',{class:'title'},[
            make('span',{class:'code',text:pid}),
            make('span',{text:p.title||pid}),
            make('span',{class:'sub',text:p.organization_name||''}),
          ]),
          make('span',{class:'meta',text:Api.fmtDate(p.start_date)+' – '+Api.fmtDate(p.end_date)}),
          make('span',{class:'count',text:'Погоджено '+all.filter(approved).length+' / '+all.length}),
        ],showProgram);
        heading.addEventListener('click',()=>toggle(key));card.appendChild(heading);
        if(showProgram){
          const body=make('div',{class:'prog-body'});
          body.appendChild(make('div',{class:'prog-tools'},[
            make('div',{class:'small muted',text:'Код '+pid+(p.approval_reference?' · '+p.approval_reference:'')}),
            make('span',{class:'small muted',text:all.length+' заходів у програмі'}),
          ]));
          const bySection={};all.forEach(m=>(bySection[m.section_id]||(bySection[m.section_id]=[])).push(m));
          Object.entries(bySection).sort((x,y)=>Api.compareSections(x[0],y[0])).forEach(([sid,rows])=>{
            const sectionKey='s:'+pid+':'+sid, showSection=inspectMode||expanded.has(sectionKey);
            const section=make('section',{class:'sec'});
            const dates=rows.map(x=>x.deadline_on).filter(Boolean).sort();
            const sectionHead=head([
              make('span',{class:'title',text:Api.sectionTitle(window.coordSections||{},sid)}),
              make('span',{class:'meta',text:dates.length?'Строк до '+Api.fmtDate(dates[dates.length-1]):'Постійні / періодичні'}),
              make('span',{class:'count',text:'Погоджено '+rows.filter(approved).length+' / '+rows.length}),
            ],showSection);
            sectionHead.addEventListener('click',()=>toggle(sectionKey));section.appendChild(sectionHead);
            if(showSection){
              const secBody=make('div',{class:'sec-body'});
              rows.sort(Api.byMeasureOrder).forEach(m=>{
                const mKey='m:'+m.id,showMeasure=inspectMode||expanded.has(mKey);
                const node=make('div',{class:'measure',id:'measure-'+m.id});
                const mHead=head([
                  make('span',{class:'num',text:Api.measureNo(m)}),
                  make('span',{text:m.description}),
                  make('span',{class:'meta',text:Api.fmtDate(m.deadline_on)||m.deadline_description||'—'}),
                  make('span',{class:'role-badge '+(approved(m)?'approved':pending(m)?'pending':'none'),text:statusLabel(m)}),
                ],showMeasure);
                mHead.addEventListener('click',()=>toggle(mKey));node.appendChild(mHead);
                if(showMeasure){
                  const detail=make('div',{class:'detail coord-original-detail'});
                  detail.appendChild(make('p',{class:'small muted',text:'Підрозділ: '+Api.deptName(m.responsible_department_id)+' · Строк: '+(Api.fmtDate(m.deadline_on)||m.deadline_description||'—')}));
                  const assignedRows=assigned(m);
                  detail.appendChild(make('p',{class:'small muted',text:'Призначено виконавців: '+assignedRows.length+' · Погоджено '+approvedCount(m)+' із '+assignedRows.length}));
                  if(!assignedRows.length){
                    detail.appendChild(make('p',{class:'small muted',text:'Виконавців ще не призначено.'}));
                  }
                  assignedRows.forEach(a=>{
                    const ex=ownSubmission(m,a.user_id),status=Api.statusOf(ex);
                    const line=make('div',{class:'coord-executor-line'});
                    const top=make('div',{class:'coord-executor-heading'},[
                      make('strong',{text:(a.login||'Виконавець #'+a.user_id)+' · '+Api.deptName(a.department_id)}),
                      make('span',{class:'role-badge '+(ex?.status||'none'),text:ex?.document_changed?'Наказ змінено':Api.STATUS[status].label}),
                    ]);
                    line.appendChild(top);
                    if(ex){
                      line.appendChild(make('div',{class:'small muted',text:'Наказ № '+(ex.order_number||'—')+' · Подано '+(Api.fmtDate(ex.submitted_at)||'—')+' · Заявка #'+ex.id}));
                      if(ex.rejection_reason)line.appendChild(make('div',{class:'role-message error',text:'Причина відхилення: '+ex.rejection_reason}));
                      if(ex.document_changed)line.appendChild(make('div',{class:'role-message error',text:'Версію наказу змінено. Виконавець має подати наказ повторно.'}));
                    }else{
                      line.appendChild(make('div',{class:'small muted',text:'Не подано. Очікується підтвердження виконання.'}));
                    }
                    const rowActions=make('div',{class:'role-actions coord-executor-actions'});
                    const action=(label,cb,variant)=>{
                      const button=make('button',{type:'button',class:'btn '+(variant||''),text:label});
                      button.addEventListener('click',cb);rowActions.appendChild(button);
                    };
                    if(ex&&ex.document_api_path){
                      action('Переглянути наказ',()=>Api.openProtected(ex.document_api_path).catch(fail),'btn-outline-secondary');
                    }
                    if(ex&&ex.status==='pending'&&!ex.document_changed){
                      action('Погодити',()=>review(m,ex,true),'btn-success');
                      action('Відхилити',()=>review(m,ex,false),'btn-outline-danger');
                    }
                    line.appendChild(rowActions);
                    detail.appendChild(line);
                  });
                  const orphaned=submissions(m).filter(ex=>!assignedRows.some(a=>Number(a.user_id)===Number(ex.submitted_by_user_id)));
                  if(orphaned.length){
                    detail.appendChild(make('p',{class:'small muted',text:'Архів подань виконавців зі скасованими призначеннями: '+orphaned.length+' (не впливають на підсумок).'}));
                  }
                  const actions=make('div',{class:'role-actions'});
                  const assignButton=make('button',{type:'button',class:'btn',text:'Призначення виконавців'});
                  assignButton.addEventListener('click',()=>openAssign(m));actions.appendChild(assignButton);
                  detail.appendChild(actions);node.appendChild(detail);
                }
                secBody.appendChild(node);
              });section.appendChild(secBody);
            }
            body.appendChild(section);
          });card.appendChild(body);
        }
        host.appendChild(card);
      });
    }
  function jump(id){$('search').value=id;selectedFilter='all';render();const node=$('measure-'+id);if(node)node.scrollIntoView({behavior:'smooth',block:'center'});}
  async function load(){
    Api.showError(null);
    try {
      const mine=await Api.get(route+'/my/programs');
      const permitted=(mine||[]).filter(x=>x.access_type==='department_coordinator');
      const response=await Promise.all(permitted.map(async function(p){
        const url=route+'/programs/'+encodeURIComponent(p.id);
        const [full,rows]=await Promise.all([Api.get(url),Api.measures(p.id)]);
        return {program:full,measures:rows};
      }));
      programs=response.map(x=>x.program);byProgram=Object.fromEntries(programs.map(x=>[x.id,x]));
      measures=response.flatMap(x=>x.measures);
      window.coordSections=await Api.sections(programs.map(p=>p.id));
      // Назви лише доступних підрозділів через workflow, а не ADMIN-only довідник.
      const ownDepartments=await Promise.all(programs.map(p=>
        Api.optional(Api.get(route+'/programs/'+encodeURIComponent(p.id)+'/available-departments'))));
      ownDepartments.forEach(result=>{if(result.ok)(result.data||[]).forEach(d=>{
        Api.DEPARTMENTS[d.id]=d.name;
      });});
      const me=Api.me; $('unit-name').textContent=Api.deptName(me.department_id);
      $('coord-kind').textContent='Координатор підрозділу';
      $('coord-help').textContent='Призначайте виконавців і перевіряйте підтвердження зареєстрованими наказами.';
      $('assign-open').classList.remove('hidden');
      Api.fillPeriods($('period'),programs);
      await refresh();
      if(!flagsPanel){flagsPanel=RiskFlagPanel.mount('coord-risk-panel',()=>programs,()=>$('period').value,jump);}
      await flagsPanel.refresh();
      if(!reportPanel && $('coord-report-panel'))reportPanel=ReportPanel.mount('coord-report-panel',()=>programs,()=>$('period').value);
      if(reportPanel)await reportPanel.refresh();
    }catch(err){fail(err);}
  }
  async function refresh(){
    try {
      const period=$('period').value;
      const [rows,events]=await Promise.all([
        Api.getAll('/api/executions/?period='+encodeURIComponent(period),500,'offset'),
        Api.optional(Api.get('/api/order-change-alerts/?limit=100')),
      ]);
      executions={};
      rows.forEach(r=>(executions[r.measure_id]||(executions[r.measure_id]=[])).push(r));
      const results=await Promise.all(measures.map(m=>Api.optional(Api.get(route+'/measures/'+encodeURIComponent(m.id)+'/assignment-people'))));
      assignments=Object.fromEntries(measures.map((m,i)=>[m.id,results[i].data||[]]));
      alerts=(events.data&&events.data.alerts)||[];
      render();renderAlerts();
      if(flagsPanel)await flagsPanel.refresh();
      if(reportPanel)await reportPanel.refresh();
    }catch(err){fail(err);}
  }
  function renderAlerts(){
    const box=$('coord-alert-panel');box.replaceChildren();
    if(!alerts.length)box.appendChild(make('p',{class:'role-empty',text:'Повідомлень про зміни наказів немає.'}));
    alerts.slice(0,30).forEach(a=>{
      const card=make('div',{class:'role-card'});
      card.appendChild(make('strong',{text:'Наказ № '+(a.order_number||a.order_id)+' · '+a.measure_id}));
      card.appendChild(make('p',{class:'role-muted',text:'Версія '+a.previous_version_number+' → '+a.new_version_number+' · '+Api.fmtDate(a.created_at)+(a.is_read?' · прочитано':' · нове')}));
      const actions=make('div',{class:'role-actions'});
      [['Попередній файл','previous'],['Новий файл','new']].forEach(([name,key])=>{
        const btn=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:name});btn.addEventListener('click',()=>Api.downloadProtected('/api/order-change-alerts/'+a.id+'/files/'+key,'order-'+a.order_id+'-'+key).catch(fail));actions.appendChild(btn);
      });
      if(!a.is_read){const btn=make('button',{type:'button',class:'btn btn-sm btn-dark',text:'Позначити прочитаним'});
        btn.addEventListener('click',async()=>{try{await Api.post('/api/order-change-alerts/'+a.id+'/read');await refresh();}catch(err){fail(err);}});actions.appendChild(btn);}
      card.appendChild(actions);box.appendChild(card);
    });
    if(window.Notify){
      const list=[...measures.flatMap(m=>submissions(m).filter(ex=>ex.status==='pending'&&!ex.document_changed).map(ex=>({lvl:'review',what:'Погодження очікує рішення',which:'Захід '+m.id+' · виконавець #'+ex.submitted_by_user_id,go:()=>jump(m.id)}))),
        ...alerts.filter(a=>!a.is_read).map(a=>({lvl:'rework',what:'Змінено наказ',which:'Захід '+a.measure_id,go:()=>jump(a.measure_id)}))];
      Notify.render(list,'Немає нових подань або змін наказів.');
    }
  }
  function review(m,ex,approve){
    if(!ex||ex.status!=='pending'||ex.document_changed)return;
    const dlg=$('coord-review-dialog');$('coord-review-title').textContent=approve?'Погодити виконання':'Відхилити подання';
    $('coord-review-details').textContent='Захід '+m.id+' · Виконавець #'+ex.submitted_by_user_id+' · Наказ № '+ex.order_number+' · '+ex.period;
    $('coord-review-reason-label').hidden=approve;
    $('coord-review-reason').value='';$('coord-review-reason').required=!approve;
    $('coord-review-message').textContent='';dlg.dataset.execution=String(ex.id);dlg.dataset.approve=approve?'1':'0';dlg.showModal();
  }
  async function sendReview(ev){ev.preventDefault();const dlg=$('coord-review-dialog');
    const exId=Number(dlg.dataset.execution);if(!Number.isSafeInteger(exId)||exId<1)return;
    const approve=dlg.dataset.approve==='1';const url=Api.executionUrl(exId);
    const reason=$('coord-review-reason').value.trim();
    if(!approve&&reason.length<3){$('coord-review-message').textContent='Вкажіть причину довжиною від 3 символів.';return;}
    const btn=$('coord-review-submit');btn.disabled=true;
    try{await (approve?Api.post(url+'/approve',{}):Api.post(url+'/reject',{reason}));
      dlg.close();notice(approve?'Подання виконавця погоджено':'Подання виконавця відхилено');await refresh();}
    catch(err){$('coord-review-message').textContent=err.message;}
    finally{btn.disabled=false;}
  }
  // Assignment panel: current assignments, department tree, VYK selector.
  let editing=null,available=[];
  async function openAssign(m){
    editing=m;
    if(!m){m=measures[0];editing=m;}
    if(!m){notice('Ще немає заходів для призначення',true);return;}
    $('assign-search').value=m.id;
    try{
      available=await Api.get(route+'/programs/'+encodeURIComponent(m.program_id)+'/available-departments');
      available.forEach(d=>Api.DEPARTMENTS[d.id]=d.name);
      drawAssign();$('assign-dialog').showModal();
    }catch(err){fail(err);}
  }
  function drawAssign(){
    const box=$('assign-body');box.replaceChildren();if(!editing)return;
    box.appendChild(make('h3',{text:'Захід '+editing.id+' · '+editing.description}));
    const measurePicker=make('select',{class:'role-field','aria-label':'Оберіть захід для призначення'});
    measures.forEach(m=>measurePicker.appendChild(make('option',{value:m.id,text:m.id+' · '+m.description.slice(0,85)})));
    measurePicker.value=editing.id;
    measurePicker.addEventListener('change',async()=>{
      const m=measures.find(x=>x.id===measurePicker.value);if(!m)return;
      editing=m;$('assign-search').value=m.id;
      try{available=await Api.get(route+'/programs/'+encodeURIComponent(m.program_id)+'/available-departments');
        available.forEach(d=>Api.DEPARTMENTS[d.id]=d.name);drawAssign();}catch(err){fail(err);}
    });
    box.append(make('label',{class:'role-form-label',text:'Оберіть захід'}),measurePicker);
    const dep=make('select',{id:'assign-department',class:'role-field','aria-label':'Підрозділ виконавця'});
    available.forEach(d=>dep.appendChild(make('option',{value:d.id,text:d.name+' ('+d.id+')'})));
    const people=make('select',{id:'assign-person',class:'role-field','aria-label':'Виконавець'});
    const reload=async()=>{
      people.replaceChildren(make('option',{value:'',text:'Завантаження…'}));
      if(!dep.value)return;
      try{
        const users=await Api.get(route+'/programs/'+encodeURIComponent(editing.program_id)+'/departments/'+encodeURIComponent(dep.value)+'/executors');
        people.replaceChildren(make('option',{value:'',text:users.length?'Оберіть виконавця':'Виконавців немає'}));
        users.forEach(u=>people.appendChild(make('option',{value:u.id,text:u.login+' (#'+u.id+')'})));
      }catch(err){people.replaceChildren(make('option',{value:'',text:err.message}));}
    };
    dep.addEventListener('change',reload);
    box.append(make('label',{class:'role-form-label',text:'Підрозділ'}),dep,make('label',{class:'role-form-label',text:'Виконавець'}),people);
    reload();
    const current=make('div',{class:'mt-3'});
    current.appendChild(make('h3',{text:'Чинні призначення'}));
    const assignmentsHere=assignments[editing.id]||[];
    if(!assignmentsHere.length)current.appendChild(make('p',{class:'small muted',text:'Поки немає призначень.'}));
    assignmentsHere.forEach(a=>{
      const row=make('div',{class:'d-flex justify-content-between align-items-center gap-2 border-bottom py-2'},[
        make('span',{text:(a.login||'Користувач #'+a.user_id)+' · '+Api.deptName(a.department_id)})]);
      const revoke=make('button',{type:'button',class:'btn btn-sm btn-outline-danger',text:'Відкликати'});
      revoke.addEventListener('click',async()=>{
        if(!confirm('Відкликати призначення користувача #'+a.user_id+'?'))return;
        try{await Api.del(route+'/measures/'+editing.id+'/assign/'+a.user_id);notice('Призначення відкликано');await refresh();drawAssign();}
        catch(err){fail(err);}
      });row.appendChild(revoke);current.appendChild(row);
    });box.appendChild(current);
  }
  async function saveAssign(){if(!editing)return;
    const dep=$('assign-department'),person=$('assign-person');if(!dep?.value||!person?.value){$('assign-msg').textContent='Оберіть підрозділ і виконавця.';return;}
    try{await Api.post(route+'/measures/'+editing.id+'/assign',{department_id:dep.value,user_id:Number(person.value)});
      notice('Виконавця призначено');await refresh();drawAssign();}
    catch(err){$('assign-msg').textContent=err.message;}
  }
  async function init(){if(!await Api.requireRole('KOORD'))return;
    ['search'].forEach(id=>$(id).addEventListener('input',render));
    $('period').addEventListener('change',refresh);
    $('coord-refresh').addEventListener('click',load);
    document.querySelectorAll('[data-coord-filter]').forEach(btn=>btn.addEventListener('click',()=>{selectedFilter=btn.dataset.coordFilter;render();}));
    document.querySelectorAll('[data-target-filter]').forEach(btn=>btn.addEventListener('click',()=>{selectedFilter=btn.dataset.targetFilter;render();}));
    $('coord-toast-close').addEventListener('click',()=>$('coord-toast').classList.add('hidden'));
    $('coord-clear-search').addEventListener('click',()=>{$('search').value='';render();});
    $('assign-open').addEventListener('click',()=>openAssign(measures[0]));
    $('assign-search').addEventListener('input',function(){
      const v=this.value.trim().toLowerCase();if(!v)return;
      const matching=measures.find(m=>(m.id+' '+m.description).toLowerCase().includes(v));
      if(matching&&matching.id!==editing?.id){$('assign-msg').textContent='Знайдено захід '+matching.id+' — оберіть його зі списку вище.';}
    });
    $('assign-cancel').addEventListener('click',()=>$('assign-dialog').close());
    $('assign-save').addEventListener('click',saveAssign);
    $('coord-review-form').addEventListener('submit',sendReview);
    $('coord-review-cancel').addEventListener('click',()=>$('coord-review-dialog').close());
    await load();
  }
  init();
})();
