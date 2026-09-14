import type { State } from './model'

export const economicPosition = (netPosition: number) => ({ netPosition,
  spendableBalance: Math.max(0, netPosition), coinDebt: Math.max(0, -netPosition) })
export const netPositionOf = (s: Pick<State, 'ledger'>, userId: string) =>
  s.ledger.filter(l => l.userId === userId).reduce((sum, l) => sum + l.amount, 0)
export const balanceOf = (s: Pick<State, 'ledger'>, userId: string) => economicPosition(netPositionOf(s, userId)).spendableBalance
export const coinDebtOf = (s: Pick<State, 'ledger'>, userId: string) => economicPosition(netPositionOf(s, userId)).coinDebt
