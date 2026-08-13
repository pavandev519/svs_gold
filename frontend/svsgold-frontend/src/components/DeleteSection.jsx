import React, { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Calculator,
  ChevronDown,
  CreditCard,
  Diamond,
  FileText,
  FolderOpen,
  Loader,
  Phone,
  ReceiptText,
  Repeat,
  Search,
  Trash2
} from 'lucide-react'
import { applicationsAPI, deletionsAPI } from '../api/api'

const emptyCounts = { applications: 0, ornaments: 0, estimation: 0, transactions: 0, invoices: 0 }

const actions = {
  applications: 'Application & All Related Records',
  ornaments: 'Ornaments',
  estimation: 'Estimation',
  transactions: 'Transactions',
  invoices: 'Invoices'
}

const formatCurrency = (value) => {
  if (value === undefined || value === null || value === '') return null
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2
  }).format(Number(value || 0))
}

const formatDate = (value) => {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).format(date)
}

const hasValue = (value) => value !== undefined && value !== null && value !== '' && value !== '-'

const compactFields = (fields) => fields.filter((field) => hasValue(field.value))

const getApplicationId = (application) => application?.application_id || application?.id || ''

const getApplicationNo = (application) => (
  application?.application_no ||
  application?.application_number ||
  application?.applicationNumber ||
  application?.app_no ||
  application?.appNo ||
  ''
)

const getApplicationLabel = (application, fallback = '') => (
  getApplicationNo(application) || fallback || getApplicationId(application) || 'Application'
)

const getAppBranch = (application) => application?.branch || application?.branch_name || application?.place

const getAppDate = (application) => (
  application?.application_date ||
  application?.applied_on ||
  application?.created_at
)

export default function DeleteSectionRedesigned() {
  const [searchMode, setSearchMode] = useState('mobile')
  const [query, setQuery] = useState('')
  const [applications, setApplications] = useState([])
  const [selectedAppId, setSelectedAppId] = useState('')
  const [selectedAppMeta, setSelectedAppMeta] = useState(null)
  const [selectedAction, setSelectedAction] = useState('applications')
  const [previewResult, setPreviewResult] = useState(null)
  const [result, setResult] = useState(null)
  const [counts, setCounts] = useState(emptyCounts)
  const [statusMessage, setStatusMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loadingAppId, setLoadingAppId] = useState(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  const normalizedQuery = query.trim()
  const isInvoiceSearch = searchMode === 'invoice'
  const selectedInvoiceNo = isInvoiceSearch && previewResult?.invoice_no ? previewResult.invoice_no : ''
  const invoiceDetail = previewResult?.invoice_details?.[0] || null

  const selectedAppLabel = getApplicationLabel(selectedAppMeta, selectedAppId)
  const hasSelectedApp = Boolean(selectedAppId && selectedAppMeta)
  const canDelete = Boolean(selectedInvoiceNo || hasSelectedApp)

  // Invoice context used in multiple places (keep at component scope to avoid runtime refs)
  const invoiceNumbersArr = previewResult?.invoice_numbers || previewResult?.deletions?.invoice_numbers || previewResult?.actionPreview?.invoice_numbers || null
  const invoiceDetailAmount = previewResult?.invoice_details?.[0]?.total_net_amount ?? null
  const invoiceValueFromSources = previewResult?.actionPreview?.invoice_value ?? previewResult?.deletions?.invoice_value ?? previewResult?.invoice_value ?? null
  let invoiceValue = null
  if (invoiceDetailAmount != null) {
    invoiceValue = invoiceDetailAmount
  } else if (Array.isArray(invoiceNumbersArr)) {
    invoiceValue = invoiceNumbersArr.length === 1 ? invoiceValueFromSources : null
  } else {
    invoiceValue = invoiceValueFromSources
  }

  // For application info view, use previewResult.application merged with initial search data; for invoice views, use invoice_details
  const initialAppFromSearch = applications.find((app) => String(getApplicationId(app)) === String(selectedAppId))
  const previewAppData = selectedAction === 'applications' 
    ? (previewResult?.application || previewResult?.deletions?.application_details || previewResult?.deletions?.applications?.[0] || initialAppFromSearch || {})
    : (previewResult?.invoice_details?.[0] || previewResult?.actionPreview?.invoice_details?.[0] || previewResult?.deletions?.invoice_details?.[0] || {})
  // Merge all available data sources in priority order
  const currentApp = { ...initialAppFromSearch, ...previewAppData, ...selectedAppMeta }
  const actionHeading = selectedAction === 'applications' ? 'Application Information' : `${actions[selectedAction]}`
  const actionPreviewData = previewResult?.actionPreview || (isInvoiceSearch ? previewResult : previewResult?.deletions)
  const isActionPreview = selectedAction !== 'applications'
  const loadingOverlay = isLoading && !result
  const loadingLabel = loadingAppId
    ? 'Loading application details...'
    : selectedAction === 'applications'
      ? 'Loading application details...'
      : `Loading ${actions[selectedAction]} preview...`

  const resetData = (nextQuery = query) => {
    setQuery(nextQuery)
    setApplications([])
    setSelectedAppId('')
    setSelectedAppMeta(null)
    setPreviewResult(null)
    setResult(null)
    setCounts(emptyCounts)
    setStatusMessage('')
    setErrorMessage('')
    setSelectedAction('applications')
  }

  const resetForMode = (mode) => {
    setSearchMode(mode)
    resetData('')
  }

  const fetchCounts = async (mobile, appId, mergedPreview = null) => {
    const [invoiceResp, transactionResp] = await Promise.all([
      deletionsAPI.previewInvoices(mobile, appId).catch(() => null),
      deletionsAPI.previewTransactions(mobile, appId).catch(() => null)
    ])

    const ornamentCount = Array.isArray(mergedPreview?.ornaments) ? mergedPreview.ornaments.length : 0
    const estimationCount = Array.isArray(mergedPreview?.estimation?.items)
      ? mergedPreview.estimation.items.length
      : mergedPreview?.estimation ? 1 : 0

    return {
      applications: mergedPreview?.application ? 1 : 0,
      ornaments: ornamentCount,
      estimation: estimationCount,
      transactions: transactionResp?.data?.deleted_items ?? transactionResp?.data?.transaction_items?.length ?? 0,
      invoices: invoiceResp?.data?.deleted_invoices ?? invoiceResp?.data?.invoice_numbers?.length ?? 0
    }
  }

  const loadApplicationDetails = async (appId, mobile = normalizedQuery) => {
    if (!appId || !mobile) return
    setLoadingAppId(appId)
    setIsLoading(true)
    setErrorMessage('')
    setStatusMessage('')
    setSelectedAction('applications')

    try {
      const [appPreviewResp, ornamentsResp, estimationResp, transactionsResp, deletionResp] = await Promise.all([
        applicationsAPI.getApplicationPreview(mobile, appId).catch(() => null),
        applicationsAPI.getOrnamentsByApplication(mobile, appId).catch(() => null),
        applicationsAPI.getEstimationPreview(mobile, appId).catch(() => null),
        import('../api/api').then(({ transactionsAPI }) => transactionsAPI.getAll(mobile)).catch(() => null),
        deletionsAPI.previewApplications(mobile, appId).catch(() => null)
      ])

      const merged = {
        application: appPreviewResp?.data || applications.find((app) => String(getApplicationId(app)) === String(appId)) || null,
        ornaments: ornamentsResp?.data?.ornaments || ornamentsResp?.data || [],
        estimation: estimationResp?.data || null,
        transactions: transactionsResp?.data || [],
        deletions: deletionResp?.data || null
      }

      setSelectedAppId(appId)
      setSelectedAppMeta(merged.application)
      setPreviewResult(merged)
      setResult(null)

      const nextCounts = await fetchCounts(mobile, appId, merged)
      setCounts(nextCounts)
      setStatusMessage(`Loaded ${getApplicationLabel(merged.application, appId)} and related records.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Failed to load application details')
    } finally {
      setIsLoading(false)
      setLoadingAppId(null)
    }
  }

  const handleSearch = async () => {
    const value = normalizedQuery
    setErrorMessage('')
    setStatusMessage('')
    setResult(null)
    setPreviewResult(null)

    if (!value) {
      setErrorMessage(searchMode === 'mobile' ? 'Enter a 10-digit mobile number.' : 'Enter an invoice number.')
      return
    }

    setIsLoading(true)
    try {
      if (searchMode === 'mobile') {
        if (!/^[0-9]{10}$/.test(value)) {
          setErrorMessage('Enter a valid 10-digit mobile number.')
          return
        }

        const appsResp = await applicationsAPI.getApplicationsByUser(value)
        const appList = appsResp?.data?.applications || []
        setApplications(appList)
        setCounts({ ...emptyCounts, applications: appList.length })
        setSelectedAppId('')
        setSelectedAppMeta(null)

        if (appList.length === 1) {
          await loadApplicationDetails(getApplicationId(appList[0]), value)
        } else if (appList.length > 1) {
          setStatusMessage(`${appList.length} applications found. Select one to load details.`)
        } else {
          setStatusMessage('No applications found for this mobile number.')
        }
        return
      }

      const invoiceResp = await deletionsAPI.previewInvoices(null, null, 'vinay', value)
      const data = invoiceResp?.data || {}
      setApplications([])
      setSelectedAppId('')
      setSelectedAppMeta(null)
      setSelectedAction('invoices')
      setPreviewResult(data)
      setCounts({
        ...emptyCounts,
        invoices: data.deleted_invoices || 0,
        transactions: data.deleted_items || 0
      })
      setStatusMessage(data.deleted_invoices ? `Loaded invoice ${value}.` : `No invoice found for ${value}.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Search failed')
    } finally {
      setIsLoading(false)
    }
  }

  const previewAction = async (action) => {
    setSelectedAction(action)
    setErrorMessage('')
    setStatusMessage('')

    if (isInvoiceSearch) {
      if (action !== 'invoices') {
        setErrorMessage('Invoice search can delete invoice records directly. Search by mobile to delete application-level records.')
        return
      }
      await handleSearch()
      return
    }

    if (!hasSelectedApp) {
      setErrorMessage('Select an application first.')
      return
    }

    setIsLoading(true)
    try {
      const basePreview = {
        ...(previewResult || {}),
        application: previewResult?.application || selectedAppMeta,
        ornaments: previewResult?.ornaments || [],
        estimation: previewResult?.estimation || null,
        deletions: previewResult?.deletions || null
      }

      let response
      if (action === 'applications') {
        response = await deletionsAPI.previewApplications(normalizedQuery, selectedAppId)
        setPreviewResult({ ...basePreview, deletions: response?.data || null, actionPreview: null })
      } else if (action === 'transactions') {
        response = await deletionsAPI.previewTransactions(normalizedQuery, selectedAppId)
        setPreviewResult({ ...basePreview, actionPreview: response?.data || null })
      } else if (action === 'invoices') {
        response = await deletionsAPI.previewInvoices(normalizedQuery, selectedAppId)
        setPreviewResult({ ...basePreview, actionPreview: response?.data || null })
      } else if (action === 'ornaments') {
        setPreviewResult({ ...basePreview, actionPreview: { ornaments: basePreview.ornaments || [] } })
      } else if (action === 'estimation') {
        setPreviewResult({ ...basePreview, actionPreview: { estimation: basePreview.estimation || null } })
      }
      setStatusMessage(`Previewing ${actions[action]}.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Preview failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    setErrorMessage('')
    setStatusMessage('')
    setIsLoading(true)

    try {
      let response
      if (isInvoiceSearch) {
        response = await deletionsAPI.deleteInvoices(null, null, 'vinay', normalizedQuery)
      } else {
        if (selectedAction === 'applications') response = await deletionsAPI.deleteApplications(normalizedQuery, selectedAppId)
        if (selectedAction === 'transactions') response = await deletionsAPI.deleteTransactions(normalizedQuery, selectedAppId)
        if (selectedAction === 'invoices') response = await deletionsAPI.deleteInvoices(normalizedQuery, selectedAppId)
      }

      setResult(response?.data || {})
      setPreviewResult(null)
      setStatusMessage(`${isInvoiceSearch ? 'Invoice' : actions[selectedAction]} deletion completed.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Delete failed')
    } finally {
      setIsLoading(false)
      setShowConfirmModal(false)
      setConfirmText('')
    }
  }

  const selectedSummary = useMemo(() => {
    if (isInvoiceSearch && invoiceDetail) {
      return compactFields([
        { label: 'Invoice Number', value: invoiceDetail.invoice_no },
        { label: 'Customer Name', value: invoiceDetail.customer_name },
        { label: 'Mobile Number', value: invoiceDetail.mobile },
        { label: 'Application No', value: invoiceDetail.application_no },
        { label: 'Application Type', value: invoiceDetail.application_type },
        { label: 'Invoice Date', value: formatDate(invoiceDetail.invoice_date) },
        { label: 'Invoice Value', value: formatCurrency(invoiceDetail.total_net_amount) },
        { label: 'Payment Status', value: invoiceDetail.payment_status || invoiceDetail.application_status }
      ])
    }

    const app = currentApp || selectedAppMeta || {}
    const estimationTotal = previewResult?.estimation?.total_amount || previewResult?.estimation?.estimated_value || app.estimated_value
    const invoiceNumbersArr = previewResult?.invoice_numbers || previewResult?.deletions?.invoice_numbers || previewResult?.actionPreview?.invoice_numbers || null
    const invoiceValueFromSources = invoiceDetailAmount ?? previewResult?.actionPreview?.invoice_value ?? previewResult?.deletions?.invoice_value ?? previewResult?.invoice_value ?? null
    let invoiceValue = null
    if (invoiceDetailAmount != null) {
      invoiceValue = invoiceDetailAmount
    } else if (Array.isArray(invoiceNumbersArr)) {
      invoiceValue = invoiceNumbersArr.length === 1 ? invoiceValueFromSources : null
    } else {
      invoiceValue = invoiceValueFromSources
    }

    return compactFields([
      { label: 'Application ID', value: getApplicationLabel(app, selectedAppId) },
      { label: 'Applicant Name', value: app.customer_name || app.applicant_name },
      { label: 'Mobile Number', value: app.mobile || (/^[0-9]{10}$/.test(normalizedQuery) ? normalizedQuery : null) },
      { label: 'Application Type', value: app.application_type || app.type },
      { label: 'Applied On', value: formatDate(getAppDate(app)) },
      { label: 'Branch', value: getAppBranch(app) },
      { label: 'Status', value: app.status },
      { label: 'Total Estimation Value', value: formatCurrency(estimationTotal) },
      { label: 'Total Ornaments', value: counts.ornaments ? `${counts.ornaments} item(s)` : null },
      { label: 'Invoices', value: counts.invoices ? `${counts.invoices} invoice(s)` : null },
      { label: 'Invoice Numbers', value: invoiceNumbersArr ? (Array.isArray(invoiceNumbersArr) ? invoiceNumbersArr.join(', ') : invoiceNumbersArr) : null },
      { label: 'Total Invoiced Amount', value: invoiceValue ? formatCurrency(invoiceValue) : null }
    ])
  }, [counts, currentApp, invoiceDetail, invoiceDetailAmount, isInvoiceSearch, normalizedQuery, previewResult, selectedAppId, selectedAppMeta])

  const steps = [
    { key: 'applications', title: 'Application Info', count: counts.applications || (hasSelectedApp ? 1 : 0), icon: FileText },
    { key: 'ornaments', title: 'Ornaments', count: counts.ornaments, icon: Diamond },
    { key: 'estimation', title: 'Estimation', count: counts.estimation, icon: Calculator },
    { key: 'transactions', title: 'Transactions', count: counts.transactions, icon: Repeat },
    { key: 'invoices', title: 'Invoices', count: counts.invoices, icon: ReceiptText }
  ]

  const previewData = previewResult?.actionPreview || (isInvoiceSearch ? previewResult : previewResult?.deletions)
  const previewSections = buildPreviewSections(previewData)

  return (
    <div className="min-h-full bg-[#f7f4ef] px-4 py-5">
      <div className="mx-auto max-w-7xl space-y-5 relative">
        {(loadingAppId || loadingOverlay) && (
          <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-white/70 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-slate-200 bg-white/95 px-6 py-6 shadow-lg">
              <Loader size={36} className="animate-spin text-[#a86f0d]" />
              <div className="text-sm font-semibold text-slate-900">{loadingLabel}</div>
              <div className="text-xs text-slate-500">Please wait while we prepare the selected records.</div>
            </div>
          </div>
        )}

        <section className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
          <div className="grid gap-6 lg:grid-cols-[1fr_390px]">
            <div>
              <h2 className="text-2xl font-bold text-slate-950">Deletion Center</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                Search by mobile to choose an application, or search by invoice number to delete that invoice directly.
              </p>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-2 rounded-md border border-slate-200 bg-slate-50 p-1 text-sm font-semibold">
                <button
                  type="button"
                  onClick={() => resetForMode('mobile')}
                  className={`rounded px-3 py-2 ${searchMode === 'mobile' ? 'bg-white text-[#a86f0d] shadow-sm' : 'text-slate-500'}`}
                >
                  Mobile
                </button>
                <button
                  type="button"
                  onClick={() => resetForMode('invoice')}
                  className={`rounded px-3 py-2 ${searchMode === 'invoice' ? 'bg-white text-[#a86f0d] shadow-sm' : 'text-slate-500'}`}
                >
                  Invoice
                </button>
              </div>

              <label className="block text-xs font-semibold text-slate-800">
                {searchMode === 'mobile' ? 'Customer Mobile' : 'Invoice Number'}
              </label>
              <div className="relative">
                <Phone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => resetData(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleSearch()
                    }
                  }}
                  placeholder={searchMode === 'mobile' ? 'Enter 10-digit mobile' : 'Enter invoice number'}
                  className="h-11 w-full rounded-md border border-slate-200 bg-white pl-10 pr-11 text-sm font-semibold text-slate-900 outline-none focus:border-[#b57916] focus:ring-2 focus:ring-[#b57916]/20"
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={isLoading}
                  className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-slate-500 hover:bg-stone-100 disabled:opacity-50"
                >
                  {isLoading ? <Loader size={16} className="animate-spin" /> : <Search size={16} />}
                </button>
              </div>
            </div>
          </div>
        </section>

        {applications.length > 1 && (
          <section className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-950">Select Application</h3>
                <p className="text-sm text-slate-500">Multiple applications found for this number</p>
              </div>
              <div className="relative w-72">
                <select
                  value={selectedAppId}
                  onChange={(e) => loadApplicationDetails(e.target.value)}
                  className="h-10 w-full appearance-none rounded-md border border-slate-200 bg-white px-3 pr-9 text-sm font-semibold outline-none focus:border-[#b57916] focus:ring-2 focus:ring-[#b57916]/20"
                >
                  <option value="">Select application</option>
                  {applications.map((app) => (
                    <option key={getApplicationId(app)} value={getApplicationId(app)}>{getApplicationLabel(app)}</option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {applications.map((app) => {
                const appId = getApplicationId(app)
                const selected = String(appId) === String(selectedAppId)
                return (
                  <button
                    key={appId}
                    type="button"
                    onClick={() => loadApplicationDetails(appId)}
                    className={`rounded-lg border p-4 text-left transition ${selected ? 'border-[#d39322] bg-[#fff9ec] shadow-sm' : 'border-slate-200 bg-white hover:border-[#d39322]'}`}
                  >
                    <div className="flex items-center gap-3">
                      <span className={`grid h-5 w-5 place-items-center rounded-full border text-xs ${selected ? 'border-[#b57916] bg-[#b57916] text-white' : 'border-slate-300 text-transparent'}`}>
                        {loadingAppId && String(loadingAppId) === String(appId) ? <Loader size={12} className="animate-spin" /> : (selected ? '✓' : '')}
                      </span>
                      <div className="font-semibold text-slate-950">{getApplicationLabel(app)}</div>
                    </div>
                    <div className="mt-2 inline-flex rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                      {app.application_type || app.type || 'Application'}
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-500">
                      {formatDate(getAppDate(app)) && <div><div>Applied On</div><strong className="text-slate-800">{formatDate(getAppDate(app))}</strong></div>}
                      {app.status && <div><div>Status</div><strong className="text-emerald-700">{app.status}</strong></div>}
                    </div>
                  </button>
                )
              })}
            </div>
          </section>
        )}

        {selectedSummary.length > 0 && (
          <section className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="grid h-8 w-8 place-items-center rounded-md bg-[#fff8ec] text-[#b57916]">
                  <FolderOpen size={17} />
                </span>
                <h3 className="text-base font-semibold text-slate-950">
                  {isInvoiceSearch ? 'Invoice Summary' : 'Top Application Summary'}
                </h3>
              </div>
              <span className="rounded-full bg-[#fff1d6] px-3 py-1 text-xs font-semibold text-[#a86f0d]">
                {isInvoiceSearch ? selectedInvoiceNo || normalizedQuery : selectedAppLabel}
              </span>
            </div>
            <div className="grid rounded-lg border border-slate-200 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
              {selectedSummary.map((item) => (
                <div key={item.label} className="border-b border-r border-slate-200 p-4 last:border-r-0">
                  <div className="text-xs font-medium text-slate-500">{item.label}</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">{item.value}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {(hasSelectedApp || isInvoiceSearch) && (
          <section className="rounded-lg border border-stone-200 bg-white shadow-sm">
            <div className="grid lg:grid-cols-[260px_1fr_320px]">
              <aside className="border-b border-slate-200 p-5 lg:border-b-0 lg:border-r">
                <h3 className="text-sm font-semibold text-slate-950">Delete Related Records</h3>
                <p className="mt-1 text-xs text-slate-500">Select the record group to preview before deleting.</p>
                <div className="mt-5 space-y-3">
                  {steps.filter((step) => !isInvoiceSearch || step.key === 'invoices').map((step, index) => {
                    const StepIcon = step.icon
                    const active = selectedAction === step.key
                    return (
                      <button
                        key={step.key}
                        type="button"
                        onClick={() => ['applications', 'ornaments', 'estimation', 'transactions', 'invoices'].includes(step.key) && previewAction(step.key)}
                        className={`flex w-full items-center gap-3 rounded-lg p-3 text-left transition ${active ? 'bg-[#fff4d9] text-[#a86f0d]' : 'hover:bg-slate-50'}`}
                      >
                        <span className={`grid h-8 w-8 place-items-center rounded-full border ${active ? 'border-[#b57916] bg-[#b57916] text-white' : 'border-slate-200 text-slate-500'}`}>
                          <StepIcon size={16} />
                        </span>
                        <span>
                          <span className="block text-sm font-semibold">{index + 1}. {step.title}</span>
                          <span className="text-xs text-slate-500">{step.count} record(s)</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </aside>

              <main className="p-5">
                <div className="mb-4 flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-950">{actionHeading}</h3>
                    <p className="text-sm text-slate-500">Review {selectedAction === 'applications' ? 'application' : actions[selectedAction].toLowerCase()} information before proceeding</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedAction('applications') || previewAction('applications')}
                      disabled={isLoading}
                      className="rounded-md border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Cancel Deletion
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowConfirmModal(true)}
                      disabled={!canDelete || isLoading}
                      className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      Delete {selectedAction === 'applications' ? 'Application & All Related Records' : actions[selectedAction]}
                    </button>
                  </div>
                </div>

                {isActionPreview ? (
                  <div className="rounded-lg border border-slate-200 bg-[#fbfaf8] p-6">
                    <div className="space-y-4">
                      {previewSections.map((section) => (
                        <div key={section.title} className="rounded-lg border border-slate-200 bg-white p-4">
                          <div className="text-xs font-semibold uppercase text-slate-500">{section.title}</div>
                          <div className="mt-3 space-y-2 text-sm text-slate-700">
                            {section.items.map((item) => <div key={item}>{item}</div>)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-slate-200 bg-[#fbfaf8] p-6">
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      <div className="col-span-2 lg:col-span-2">
                        <div className="grid grid-cols-2 gap-y-4 gap-x-6">
                          <div className="text-xs text-slate-500">Application ID</div>
                          <div className="font-semibold text-slate-900">{getApplicationLabel(currentApp || selectedAppMeta || {}, selectedAppId)}</div>

                          <div className="text-xs text-slate-500">Applicant Name</div>
                          <div className="font-semibold text-slate-900">{currentApp?.customer_name || currentApp?.applicant_name || currentApp?.name || '-'}</div>

                          <div className="text-xs text-slate-500">Application Type</div>
                          <div className="font-semibold text-slate-900">{currentApp?.application_type || currentApp?.type || currentApp?.app_type || '-'}</div>

                          <div className="text-xs text-slate-500">Mobile Number</div>
                          <div className="font-semibold text-slate-900">{currentApp?.mobile || currentApp?.phone || (/^[0-9]{10}$/.test(normalizedQuery) ? normalizedQuery : '-')}</div>

                          <div className="text-xs text-slate-500">Email</div>
                          <div className="font-semibold text-slate-900">{currentApp?.email || currentApp?.customer_email || currentApp?.email_id || '-'}</div>

                          <div className="text-xs text-slate-500">Applied On</div>
                          <div className="font-semibold text-slate-900">{formatDate(getAppDate(currentApp) || currentApp?.applied_on || currentApp?.created_at) || '-'}</div>

                          <div className="text-xs text-slate-500">Status</div>
                          <div className="font-semibold text-slate-900">{currentApp?.status || currentApp?.application_status || currentApp?.state || '-'}</div>

                          <div className="text-xs text-slate-500">Branch</div>
                          <div className="font-semibold text-slate-900">{getAppBranch(currentApp) || currentApp?.location || '-'}</div>

                          <div className="text-xs text-slate-500">Source</div>
                          <div className="font-semibold text-slate-900">{currentApp?.source || currentApp?.origin || currentApp?.channel || 'Walk-in'}</div>

                          <div className="text-xs text-slate-500">Remarks</div>
                          <div className="font-semibold text-slate-900">{currentApp?.remarks || currentApp?.notes || currentApp?.comments || '-'}</div>
                        </div>
                      </div>

                      <div className="col-span-1">
                        <div className="rounded-md border border-slate-100 bg-white p-4">
                          <div className="text-xs text-slate-500">Summary</div>
                          <div className="mt-2 space-y-2 text-sm text-slate-700">
                            {[
                              { label: 'Applications', value: counts.applications || (hasSelectedApp ? 1 : 0) },
                              { label: 'Invoices', value: counts.invoices },
                              { label: 'Settlements', value: previewResult?.deletions?.deleted_settlements },
                              { label: 'Invoice value', value: invoiceValue ? formatCurrency(invoiceValue) : null },
                              { label: 'Settlement value', value: previewResult?.deletions?.settlement_value ? formatCurrency(previewResult.deletions.settlement_value) : null }
                            ].filter((item) => item.value != null && item.value !== 0).map((item) => (
                              <div key={item.label}>{item.label}: {item.value}</div>
                            ))}
                          </div>
                        </div>

                        <div className="mt-4 rounded-md border border-slate-100 bg-white p-4">
                          <div className="text-xs text-slate-500">Invoices</div>
                          <div className="mt-2 text-sm font-semibold text-slate-900">{invoiceNumbersArr ? (Array.isArray(invoiceNumbersArr) ? invoiceNumbersArr.join(', ') : invoiceNumbersArr) : '-'}</div>
                        </div>

                        <div className="mt-4 rounded-md border border-slate-100 bg-white p-4">
                          <div className="text-xs text-slate-500">Ornaments</div>
                          <div className="mt-2 text-sm font-semibold text-slate-900">{counts.ornaments ? `${counts.ornaments} item(s)` : '-'}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </main>

              <aside className="border-t border-slate-200 p-5 lg:border-l lg:border-t-0">
                <h3 className="text-sm font-semibold text-slate-950">Deletion Progress</h3>
                <div className="my-6 flex justify-center">
                  <div className="grid h-24 w-24 place-items-center rounded-full border-[8px] border-slate-100">
                    <div className="text-center">
                      <div className="text-xl font-bold text-slate-950">0%</div>
                      <div className="text-xs text-slate-500">0 of {isInvoiceSearch ? 1 : 5}</div>
                    </div>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  {steps.filter((step) => !isInvoiceSearch || step.key === 'invoices').map((step) => (
                    <div key={step.key} className="flex items-center justify-between">
                      <span className="text-slate-600">{step.title}</span>
                      <span className="text-xs text-slate-400">Pending</span>
                    </div>
                  ))}
                </div>

                <div className="mt-6 rounded-lg border border-red-100 bg-red-50 p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="mt-0.5 h-5 w-5 text-red-600" />
                    <div>
                      <div className="text-sm font-semibold text-red-700">Deletion is permanent</div>
                      <div className="mt-1 text-xs text-red-600">This action cannot be undone.</div>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  disabled={!canDelete || isLoading}
                  onClick={() => setShowConfirmModal(true)}
                  className="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-red-600 px-4 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash2 size={16} />
                  Delete {isInvoiceSearch ? 'Invoice' : actions[selectedAction]}
                </button>
              </aside>
            </div>
          </section>
        )}

        {errorMessage && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <strong>Error:</strong> {errorMessage}
          </div>
        )}

        {statusMessage && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
            <strong>{result ? 'Success:' : 'Preview:'}</strong> {statusMessage}
          </div>
        )}

        {result && (
          <section className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">Delete Result</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {Object.entries(result).filter(([, value]) => hasValue(value)).map(([key, value]) => (
                <div key={key} className="rounded-md bg-slate-50 p-3 text-sm">
                  <div className="text-xs text-slate-500">{key.replace(/_/g, ' ')}</div>
                  <div className="mt-1 font-semibold text-slate-900">{Array.isArray(value) ? value.join(', ') : value}</div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowConfirmModal(false)} />
          <div className="relative z-10 w-full max-w-xl rounded-lg bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-950">Confirm Delete</h3>
            <p className="mt-2 text-sm text-slate-600">
              Type <strong>YES</strong> to delete {isInvoiceSearch ? normalizedQuery : actions[selectedAction]}.
            </p>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type YES to confirm"
              className="mt-4 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100"
            />
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowConfirmModal(false)
                  setConfirmText('')
                }}
                className="rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={confirmText !== 'YES' || isLoading}
                onClick={handleDelete}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Delete now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function buildPreviewSections(data) {
  if (!data || typeof data !== 'object') {
    return [{ title: 'Preview', items: ['Search or select an application to preview records.'] }]
  }

  const sections = []
  const summary = []

  if (typeof data.deleted_applications === 'number') summary.push(`Applications: ${data.deleted_applications}`)
  if (typeof data.deleted_invoices === 'number') summary.push(`Invoices: ${data.deleted_invoices}`)
  if (typeof data.deleted_items === 'number') summary.push(`Items: ${data.deleted_items}`)
  if (typeof data.deleted_settlements === 'number') summary.push(`Settlements: ${data.deleted_settlements}`)
  if (typeof data.deleted_calculation_entries === 'number') summary.push(`Calculation entries: ${data.deleted_calculation_entries}`)
  if (typeof data.invoice_value === 'number') summary.push(`Invoice value: ${formatCurrency(data.invoice_value)}`)
  if (typeof data.settlement_value === 'number') summary.push(`Settlement value: ${formatCurrency(data.settlement_value)}`)
  if (typeof data.transaction_value === 'number') summary.push(`Transaction value: ${formatCurrency(data.transaction_value)}`)

  if (summary.length) sections.push({ title: 'Summary', items: summary })
  if (Array.isArray(data.application_numbers) && data.application_numbers.length) sections.push({ title: 'Applications', items: data.application_numbers })
  if (Array.isArray(data.invoice_numbers) && data.invoice_numbers.length) sections.push({ title: 'Invoices', items: data.invoice_numbers })
  if (Array.isArray(data.invoice_items) && data.invoice_items.length) {
    sections.push({ title: 'Invoice Items', items: data.invoice_items.map((item) => `${item.name || 'Item'} - ${formatCurrency(item.amount)}`) })
  }
  if (Array.isArray(data.transaction_items) && data.transaction_items.length) {
    sections.push({ title: 'Transactions', items: data.transaction_items.map((item) => `${item.name || 'Item'} - ${formatCurrency(item.amount)}`) })
  }
  if (Array.isArray(data.settlements) && data.settlements.length) {
    sections.push({ title: 'Settlements', items: data.settlements.map((item) => `${item.mode || 'Payment'} - ${formatCurrency(item.amount)}`) })
  }
  if (Array.isArray(data.ornaments) && data.ornaments.length) {
    sections.push({ title: 'Ornaments', items: data.ornaments.map((item) => `${item.name || item.description || 'Ornament'}${item.quantity ? ` x${item.quantity}` : ''}`) })
  }
  if (data.estimation) {
    if (Array.isArray(data.estimation.items) && data.estimation.items.length) {
      sections.push({ title: 'Estimation', items: data.estimation.items.map((item) => `${item.name || item.description || item.type || 'Item'} - ${formatCurrency(item.amount || item.value || item.net_amount)}`) })
    } else {
      const estimationItems = []
      if (typeof data.estimation.total_amount !== 'undefined') estimationItems.push(`Total: ${formatCurrency(data.estimation.total_amount)}`)
      if (typeof data.estimation.estimated_value !== 'undefined') estimationItems.push(`Estimated value: ${formatCurrency(data.estimation.estimated_value)}`)
      if (typeof data.estimation.note !== 'undefined') estimationItems.push(`Note: ${data.estimation.note}`)
      if (estimationItems.length) sections.push({ title: 'Estimation', items: estimationItems })
    }
  }

  return sections.length ? sections : [{ title: 'Preview', items: ['No records found for this selection.'] }]
}
