// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { CapabilitiesPanel } from './CapabilitiesPanel'
const mock=vi.hoisted(()=>({demo:false,values:undefined as Record<string,boolean>|undefined,put:vi.fn(),refresh:vi.fn()}))
vi.mock('../../runtime',()=>({get IS_DEMO(){return mock.demo}}))
vi.mock('../../store',()=>({useStore:()=>({state:{capabilities:mock.values},refresh:mock.refresh})}))
vi.mock('../../api',()=>({api:{put:mock.put}}))
vi.mock('../../i18n',()=>({useI18n:()=>({t:(key:string)=>key})}))
;(globalThis as Record<string,unknown>).IS_REACT_ACT_ENVIRONMENT=true
let host:HTMLDivElement,root:Root
beforeEach(()=>{mock.demo=false;mock.values={TASK_LITE:true,THANKS:true,INCENTIVE_SAFETY:true};mock.put.mockReset().mockResolvedValue({});mock.refresh.mockReset();host=document.createElement('div');document.body.append(host);root=createRoot(host)})
afterEach(async()=>{await act(async()=>root.unmount());host.remove()})
async function render(){await act(async()=>root.render(<CapabilitiesPanel/>))}
function button(key:string){return host.querySelector<HTMLButtonElement>(`[aria-label="capabilities.${key}"]`)!}
it('sends the exact server command then refreshes without optimistic local mutation',async()=>{await render();await act(async()=>button('THANKS').click());expect(mock.put).toHaveBeenCalledWith('/capabilities/THANKS',{enabled:false});expect(mock.refresh).toHaveBeenCalledOnce();expect(button('THANKS').getAttribute('aria-pressed')).toBe('true')})
it('mandatory safety cannot be disabled',async()=>{await render();expect(button('INCENTIVE_SAFETY').disabled).toBe(true);button('INCENTIVE_SAFETY').click();expect(mock.put).not.toHaveBeenCalled()})
it('missing server projection never falls back to demo',async()=>{mock.values=undefined;await render();expect(button('TASK_LITE').disabled).toBe(true);expect(host.querySelector('[role="status"]')?.textContent).toBe('capabilities.unavailable')})
it('demo is read-only and makes no API calls',async()=>{mock.demo=true;await render();for(const b of host.querySelectorAll('button')){expect(b.disabled).toBe(true);b.click()}expect(mock.put).not.toHaveBeenCalled()})
it('failed update retains projection and displays only localized feedback',async()=>{mock.put.mockRejectedValue(new Error('private backend detail'));await render();await act(async()=>button('THANKS').click());expect(host.querySelector('[role="alert"]')?.textContent).toBe('capabilities.error');expect(host.textContent).not.toContain('private backend detail');expect(mock.refresh).not.toHaveBeenCalled()})
