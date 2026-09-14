export function passwordStrength(value: string): 'weak' | 'fair' | 'good' | 'strong' {
  if (value.length < 8 || /(.)\1{3}/u.test(value) || /password|123456|qwerty|abcdef/i.test(value) || new Set(value).size < 4) return 'weak'
  const diversity = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter(r => r.test(value)).length
  if (value.length >= 12 && diversity >= 2) return 'strong'
  if (value.length >= 8 && diversity >= 3) return 'good'
  return value.length >= 10 ? 'good' : 'fair'
}
