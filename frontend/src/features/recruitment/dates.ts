export const localTimestamp = (value = new Date().toISOString()) => new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).replace(' ', 'T');
export const asShanghaiTimestamp = (value: string) => `${value.length === 16 ? `${value}:00` : value}+08:00`;
