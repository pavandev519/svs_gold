import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000
})

api.interceptors.request.use(
  config => { console.log(`[API] ${config.method.toUpperCase()} ${config.baseURL}${config.url}`); return config },
  error => Promise.reject(error)
)

api.interceptors.response.use(
  response => { console.log('[API] Response Success'); return response },
  error => { console.error(`[API Error] ${error.message}`); return Promise.reject(error) }
)

const searchCustomerCache = new Map()
const searchCustomerPromises = new Map()
const summaryCustomerCache = new Map()
const summaryCustomerPromises = new Map()
const SEARCH_CUSTOMER_TTL = 30 * 1000 // 30 seconds cache
const SUMMARY_CUSTOMER_TTL = 15 * 1000 // 15 seconds cache

const isCacheFresh = (entry) => entry && (Date.now() - entry.timestamp) < SEARCH_CUSTOMER_TTL
const isSummaryCacheFresh = (entry) => entry && (Date.now() - entry.timestamp) < SUMMARY_CUSTOMER_TTL

const normalizeInclude = (include) => {
  const values = Array.isArray(include) ? include : `${include}`.split(',')
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))].join(',')
}

const clearCachedEntriesForMobile = (mobile) => {
  const normalizedMobile = mobile?.toString().trim()
  if (!normalizedMobile) return

  searchCustomerCache.delete(normalizedMobile)
  searchCustomerPromises.delete(normalizedMobile)

  for (const key of summaryCustomerCache.keys()) {
    if (key.startsWith(`${normalizedMobile}::`)) {
      summaryCustomerCache.delete(key)
    }
  }

  for (const key of summaryCustomerPromises.keys()) {
    if (key.startsWith(`${normalizedMobile}::`)) {
      summaryCustomerPromises.delete(key)
    }
  }
}

export const accountsAPI = {
  checkAccount: (data) => api.post('/accounts/check', data),
  createAccount: (data) => api.post('/accounts/create', data),
  updateAccount: (data) => api.put('/accounts/update', data),
  addAddress: (mobile, data) => api.post(`/accounts/addresses?mobile=${mobile}`, data),
  addBankAccount: (mobile, data) => api.post(`/accounts/bank-accounts?mobile=${mobile}`, data),
  addDocument: (mobile, data) => api.post(`/accounts/documents?mobile=${mobile}`, data),
  deleteDocument: (mobile, documentId) => api.delete(`/accounts/documents?mobile=${mobile}&document_id=${documentId}`),
  searchCustomer: (mobile, { force = false } = {}) => {
    if (!mobile) return Promise.reject(new Error('Mobile is required'))

    const normalized = mobile.toString().trim()
    const cacheEntry = searchCustomerCache.get(normalized)

    if (!force && isCacheFresh(cacheEntry)) {
      return Promise.resolve({ data: cacheEntry.data })
    }

    if (!force && searchCustomerPromises.has(normalized)) {
      return searchCustomerPromises.get(normalized)
    }

    const promise = api.get(`/customers/search?mobile=${normalized}`)
      .then((res) => {
        searchCustomerCache.set(normalized, { data: res.data, timestamp: Date.now() })
        searchCustomerPromises.delete(normalized)
        return res
      })
      .catch((err) => {
        searchCustomerPromises.delete(normalized)
        throw err
      })

    searchCustomerPromises.set(normalized, promise)
    return promise
  },
  searchCustomerSummary: (mobile, include = "customer") => {
    if (!mobile) return Promise.reject(new Error('Mobile is required'))

    const normalizedMobile = mobile.toString().trim()
    const includeParam = normalizeInclude(include || 'customer') || 'customer'
    const cacheKey = `${normalizedMobile}::${includeParam}`
    const cacheEntry = summaryCustomerCache.get(cacheKey)

    if (isSummaryCacheFresh(cacheEntry)) {
      return Promise.resolve({ data: cacheEntry.data })
    }

    if (summaryCustomerPromises.has(cacheKey)) {
      return summaryCustomerPromises.get(cacheKey)
    }

    const promise = api.get(`/customers/summary?mobile=${normalizedMobile}&include=${includeParam}`)
      .then((res) => {
        summaryCustomerCache.set(cacheKey, { data: res.data, timestamp: Date.now() })
        summaryCustomerPromises.delete(cacheKey)
        return res
      })
      .catch((err) => {
        summaryCustomerPromises.delete(cacheKey)
        throw err
      })

    summaryCustomerPromises.set(cacheKey, promise)
    return promise
  },
  clearCustomerCache: (mobile) => {
    clearCachedEntriesForMobile(mobile)
  },
}

export const applicationsAPI = {
  getGoldItems: () => api.get('/gold-items'),
  getBranches: () => api.get('/branches'),
  getApplicationsByUser: (mobile) => api.get(`/applications/by-user?mobile=${mobile}`),
  getApplicationPreview: (mobile, applicationId) => api.get(`/applications/application-preview?mobile=${mobile}&application_id=${applicationId}`),
  getOrnamentsByApplication: (mobile, applicationId) => api.get(`/applications/ornaments/by-application?mobile=${mobile}&application_id=${applicationId}`),
  getEstimationPreview: (mobile, applicationId) => api.get(`/applications/estimation-preview?mobile=${mobile}&application_id=${applicationId}`),
  createApplication: (data) => api.post('/applications/create', data),
  deleteApplication: (data) => api.delete('/applications/delete', { data }),
  addPledgeDetails: (data) => api.post('/applications/pledge-details', data),
  addOrnaments: (data) => api.post('/applications/ornaments', data),
  deleteOrnament: (itemId, mobile) => api.delete(`/applications/ornaments/${itemId}?mobile=${mobile}`),
  addEstimation: (data) => api.post('/estimations/items', data),
  
}

export const paymentsAPI = {
  createInvoice: (data) => api.post('/payments/invoice/create', data),
  addInvoiceItem: (data) => api.post('/payments/invoice/item', data),
  addDeduction: (data) => api.post('/payments/deduction', data),
  addSettlement: (data) => api.post('/payments/settlement', data),
}

export const transactionsAPI = {
  getAll: (mobile, days = 30) => {
    return api.get(`/transactions/all?mobile=${encodeURIComponent(mobile || '')}&days=${days}`)
  }
}

export const estimationsAPI = {
  getByUser: (mobile) => api.get(`/estimations/by-user?mobile=${mobile}`)
}

export default api
