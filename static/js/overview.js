(() => {
    const root = document.querySelector('[data-financial-overview]');
    if (!root) return;
    const initial = JSON.parse(document.getElementById('overview-data').textContent);
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const dark = document.documentElement.dataset.theme === 'dark';
    const colors = { teal:dark?'#25d3c3':'#16785a', blue:dark?'#39afff':'#376fd0', net:dark?'#aaa0ef':'#8060c1', grid:dark?'#1d3041':'#e2ebe5', muted:dark?'#8497ae':'#6d8276', text:dark?'#f1f5f9':'#20362b', panel:dark?'#101d2c':'#ffffff' };
    const money = new Intl.NumberFormat('en-IE', {style:'currency',currency:'EUR',minimumFractionDigits:2,maximumFractionDigits:2});
    const compact = new Intl.NumberFormat('en-IE', {notation:'compact',maximumFractionDigits:1});
    const dayFormat = new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
    const axisFormat = new Intl.DateTimeFormat('en-GB',{month:'short',year:'2-digit',timeZone:'UTC'});
    const shortFormat = new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'});
    let history=initial.history, flow=initial.flow, metric='income', balanceChart, flowChart;
    let balanceRequest, flowRequest;
    function state(target, text, retry) {
        target.replaceChildren();
        target.hidden = !text;
        if (text) target.append(document.createTextNode(text));
        if (retry) {
            const button=document.createElement('button');
            button.type='button'; button.textContent='Retry'; button.addEventListener('click',retry);
            target.append(button);
        }
    }
    function options() {
        return {
            responsive:true,maintainAspectRatio:false,animation:reduced?false:{duration:200},
            interaction:{mode:'index',intersect:false},
            plugins:{legend:{display:false},tooltip:{
                backgroundColor:colors.panel,titleColor:colors.text,bodyColor:colors.text,
                borderColor:colors.grid,borderWidth:1,padding:10,displayColors:false,
                titleFont:{size:11,weight:'500'},bodyFont:{size:11},
                callbacks:{label:ctx=>ctx.dataset.label+': '+money.format(ctx.parsed.y)}
            }},
            scales:{x:{grid:{display:false},border:{display:false},ticks:{color:colors.muted,font:{size:10},maxRotation:0}},
                    y:{grid:{color:colors.grid,drawTicks:false},border:{display:false},ticks:{color:colors.muted,font:{size:9},maxTicksLimit:4,padding:6,callback:value=>'€'+compact.format(value)}}}
        };
    }
    function balancePoints(data) {
        // Carry the recorded closing balance across days with no ledger events.
        const events=data.points, points=[];
        let index=0, value=events[0].balance;
        const begin=Date.parse(data.start+'T12:00:00Z'), end=Date.parse(data.end+'T12:00:00Z');
        const day=86400000;
        for (let at=begin; at<=end; at+=day) {
            while (index+1<events.length && Date.parse(events[index+1].date+'T12:00:00Z')<=at) value=events[++index].balance;
            points.push({x:at,y:value});
        }
        return points;
    }
    function renderBalance() {
        root.querySelector('.ov-total').textContent=money.format(history.total);
        const target=root.querySelector('[data-balance-state]');
        state(target, !history.has_accounts?'Add an account to start your balance history.':history.has_future?'Review future-dated posted transactions before viewing historical balances.':'');
        if (!window.Chart) { state(target,'The local chart library could not load. Reload the page to try again.'); return; }
        if (history.has_future || !history.has_accounts) { balanceChart?.destroy(); balanceChart=null; return; }
        const points=balancePoints(history);
        const opt=options();
        opt.parsing=false;
        opt.scales.x.type='linear';
        opt.scales.x.min=points[0].x; opt.scales.x.max=points.at(-1).x;
        opt.scales.x.ticks.maxTicksLimit=6;
        opt.scales.x.ticks.callback=value=>(['1w','1m'].includes(history.period)?shortFormat:axisFormat).format(new Date(value));
        if (!['1w','1m'].includes(history.period)) opt.scales.x.afterBuildTicks=scale=>{
            const first=new Date(points[0].x), last=points.at(-1).x;
            const monthCount=(new Date(last).getUTCFullYear()-first.getUTCFullYear())*12+new Date(last).getUTCMonth()-first.getUTCMonth();
            const step=Math.max(1,Math.ceil(monthCount/6)), ticks=[{value:points[0].x}];
            const tick=new Date(points[0].x);tick.setUTCMonth(tick.getUTCMonth()+step,1);
            while(tick.getTime()<=last){ticks.push({value:tick.getTime()});tick.setUTCMonth(tick.getUTCMonth()+step);}
            scale.ticks=ticks;
        };
        opt.scales.y.position='right';
        opt.plugins.tooltip.callbacks.title=items=>dayFormat.format(new Date(items[0].parsed.x));
        const dataset={label:'Balance',data:points,borderColor:colors.teal,borderWidth:1.8,
            pointRadius:ctx=>ctx.dataIndex===points.length-1?3:0,pointHoverRadius:4,pointBackgroundColor:colors.teal,
            pointBorderWidth:0,fill:true,tension:0.12,
            backgroundColor:ctx=>{const area=ctx.chart.chartArea;if(!area)return 'transparent';const g=ctx.chart.ctx.createLinearGradient(0,area.top,0,area.bottom);g.addColorStop(0,dark?'rgba(37,211,195,.12)':'rgba(22,120,90,.12)');g.addColorStop(1,'rgba(37,211,195,0)');return g;}};
        balanceChart?.destroy();
        balanceChart=new Chart(document.getElementById('overviewBalanceChart'),{type:'line',data:{datasets:[dataset]},options:opt,
            plugins:[{id:'overviewCursor',afterDraw(chart){const active=chart.tooltip?.getActiveElements();if(!active?.length)return;const x=active[0].element.x;const c=chart.ctx;c.save();c.strokeStyle=colors.grid;c.setLineDash([3,3]);c.beginPath();c.moveTo(x,chart.chartArea.top);c.lineTo(x,chart.chartArea.bottom);c.stroke();c.restore();}}]});
        const percent=root.querySelector('[data-hero-percent]');
        if (percent) {
            percent.textContent=history.percent===null?'—':(history.percent>0?'+':'')+history.percent+'%';
            percent.className='ov-change '+(history.change>=0?'is-positive':'is-negative');
            root.querySelector('[data-hero-change]').textContent=(history.change>0?'+':'')+money.format(history.change);
            root.querySelector('[data-hero-period]').textContent={ '1w':'over 1 week','1m':'over 1 month','3m':'over 3 months','1y':'over 1 year','all':'since opening balances' }[history.period];
        }
        root.querySelector('[data-balance-accessible]').textContent=dayFormat.format(new Date(history.start+'T12:00:00Z'))+' to '+dayFormat.format(new Date(history.end+'T12:00:00Z'))+'. Current balance '+money.format(history.total)+'. Change '+money.format(history.change)+'.';
    }
    function renderFlow() {
        const target=root.querySelector('[data-flow-state]');
        const empty=!flow.rows.some(row=>row.income || row.expenses || row.investments);
        state(target,empty?'No posted cash flow in this period.':'');
        root.querySelector('[data-flow-label]').textContent='Average monthly '+{income:'income',expenses:'spending',net:'net cash flow'}[metric];
        root.querySelector('[data-flow-value]').textContent=money.format(flow.averages[metric]);
        const comparison=flow.comparisons[metric];
        root.querySelector('[data-flow-comparison]').textContent=comparison===null?'No comparable prior activity':(comparison>0?'+':'')+comparison+'% vs. previous '+flow.months+' months';
        root.querySelectorAll('[data-flow-metric]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.flowMetric===metric)));
        root.querySelector('.ov-legend-income').hidden=metric==='net';
        root.querySelector('.ov-legend-expenses').hidden=metric==='net';
        root.querySelector('.ov-legend-net').hidden=metric!=='net';
        if (!window.Chart) { state(target,'The local chart library could not load. Reload the page to try again.'); return; }
        const datasets=metric==='net'?[{label:'Net after investments',data:flow.rows.map(row=>row.net),backgroundColor:colors.net}]:
            [{label:'Income',data:flow.rows.map(row=>row.income),backgroundColor:metric==='income'?colors.teal:(dark?'#1b645d':'#9bc9bd')},
             {label:'Spending',data:flow.rows.map(row=>row.expenses),backgroundColor:metric==='expenses'?colors.blue:(dark?'#205374':'#a4c0df')}];
        datasets.forEach(dataset=>Object.assign(dataset,{borderRadius:3,maxBarThickness:16,categoryPercentage:.65,barPercentage:.8}));
        const opt=options();opt.scales.y.beginAtZero=true;opt.scales.x.ticks.maxTicksLimit=6;
        flowChart?.destroy();
        flowChart=new Chart(document.getElementById('overviewFlowChart'),{type:'bar',data:{labels:flow.rows.map(row=>row.label),datasets},options:opt});
        document.getElementById('overviewFlowChart').setAttribute('aria-label',metric==='net'?'Monthly net cash flow after investments in euros':'Monthly income and spending in euros; '+metric+' highlighted');
    }
    async function get(url,signal) {
        const response=await fetch(url,{signal,headers:{Accept:'application/json'}});
        if(!response.ok)throw new Error('Request failed');
        return response.json();
    }
    async function selectRange(range) {
        balanceRequest?.abort();const controller=new AbortController();balanceRequest=controller;
        const target=root.querySelector('[data-balance-state]');
        state(target,'Loading balance history…');target.classList.add('is-loading');
        root.querySelector('.ov-balance-visual').setAttribute('aria-busy','true');
        try {
            const data=await get('/overview/balance?range='+encodeURIComponent(range),controller.signal);
            if(!Array.isArray(data.points)||!Number.isFinite(data.total))throw new Error('Invalid balance response');
            history=data;renderBalance();
            root.querySelectorAll('[data-balance-range]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.balanceRange===history.period)));
        } catch(error) { if(error.name!=='AbortError')state(target,'Balance history could not be loaded.',()=>selectRange(range)); }
        finally { if(balanceRequest===controller){target.classList.remove('is-loading');root.querySelector('.ov-balance-visual').removeAttribute('aria-busy');} }
    }
    async function selectFlow(months) {
        flowRequest?.abort();const controller=new AbortController();flowRequest=controller;
        const target=root.querySelector('[data-flow-state]');state(target,'Loading cash flow…');root.querySelector('.ov-cashflow').setAttribute('aria-busy','true');
        try {
            const data=await get('/overview/cash-flow?months='+encodeURIComponent(months),controller.signal);
            if(!Array.isArray(data.rows)||!data.averages)throw new Error('Invalid cash flow response');
            flow=data;renderFlow();
        } catch(error) { if(error.name!=='AbortError')state(target,'Cash flow could not be loaded.',()=>selectFlow(months)); }
        finally { if(flowRequest===controller)root.querySelector('.ov-cashflow').removeAttribute('aria-busy'); }
    }
    root.querySelectorAll('[data-balance-range]').forEach(button=>button.addEventListener('click',()=>selectRange(button.dataset.balanceRange)));
    root.querySelectorAll('[data-flow-metric]').forEach(button=>button.addEventListener('click',()=>{metric=button.dataset.flowMetric;renderFlow();}));
    root.querySelector('[data-flow-months]').addEventListener('change',event=>selectFlow(event.target.value));
    const strip=root.querySelector('[data-account-strip]');
    const arrows=root.querySelectorAll('[data-accounts-scroll]');
    function updateArrows() {
        const overflow=strip.scrollWidth>strip.clientWidth+2;
        arrows.forEach(button=>{button.hidden=!overflow;button.disabled=button.dataset.accountsScroll==='-1'?strip.scrollLeft<=2:strip.scrollLeft+strip.clientWidth>=strip.scrollWidth-2;});
    }
    arrows.forEach(button=>button.addEventListener('click',()=>strip.scrollBy({left:Number(button.dataset.accountsScroll)*strip.clientWidth*.8,behavior:reduced?'instant':'smooth'})));
    strip.addEventListener('scroll',updateArrows,{passive:true});
    new ResizeObserver(updateArrows).observe(strip);updateArrows();
    root.querySelectorAll('[data-transaction-href]').forEach(row=>row.addEventListener('click',event=>{if(!event.target.closest('a,button')&&!window.getSelection().toString())location.href=row.dataset.transactionHref;}));
    root.querySelectorAll('img').forEach(img=>{
        const fallback=()=>{img.hidden=true;img.parentElement.textContent='—';};
        img.addEventListener('error',fallback);
        if(img.complete&&!img.naturalWidth)fallback();
    });
    const safe=document.querySelector('[data-safe-dialog]');
    root.querySelector('[data-safe-info]').addEventListener('click',()=>safe.showModal());
    safe.querySelector('[data-safe-close]').addEventListener('click',()=>safe.close());
    safe.addEventListener('click',event=>{if(event.target===safe){const r=safe.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)safe.close();}});
    renderBalance();renderFlow();
})();
