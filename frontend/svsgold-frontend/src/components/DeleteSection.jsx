import React, { useState, useEffect } from 'react'
import { Search, Trash2, FileText, CreditCard, RefreshCcw, ShieldCheck } from 'lucide-react'
import { deletionsAPI } from '../api/api'

const actionButtons = [
  {
    key: 'applications',
    label: 'Applications',
    description: 'Delete all application records, including pledge, ornaments, estimation mappings and calculation entries.',
    icon: FileText
  },
  {
    key: 'payments',
    label: 'Payments',
    description: 'Delete payment settlement records for this customer.',
    icon: CreditCard
  },
  {
    key: 'invoices',
    label: 'Invoices',
    description: 'Delete invoice headers and all related items / settlements.',
    icon: Trash2
  },
  {
    key: 'transactions',
    label: 'Transactions',
    description: 'Delete transaction-level invoice items, settlements and linked calculation entries.',
    icon: RefreshCcw
  },
  {
    key: 'all',
    label: 'Full Purge',
    description: 'Run a complete bottom-up cleanup for the customer mobile.',
    icon: ShieldCheck
  }
]

const actionDisplay = {
  applications: 'Applications',
  payments: 'Payments',
  invoices: 'Invoices',
  transactions: 'Transactions',
  all: 'Full purge'
}

const formatCurrency = (value) => {
  const numericValue = Number(value || 0)
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2
  }).format(numericValue)
}

const buildPreviewSections = (data) => {
  if (!data || typeof data !== 'object') {
    return [{ title: 'Delete impact', items: ['No preview data available.'] }]
  }

  const sections = []
  const summaryItems = []

  if (typeof data.deleted_applications === 'number') {
    summaryItems.push({ label: 'Applications', value: data.deleted_applications })
  }
  if (typeof data.deleted_invoices === 'number') {
    summaryItems.push({ label: 'Invoices', value: data.deleted_invoices })
  }
  if (typeof data.deleted_items === 'number') {
    summaryItems.push({ label: 'Invoice items', value: data.deleted_items })
  }
  if (typeof data.deleted_settlements === 'number') {
    summaryItems.push({ label: 'Settlements', value: data.deleted_settlements })
  }
  if (typeof data.deleted_calculation_entries === 'number') {
    summaryItems.push({ label: 'Calculation entries', value: data.deleted_calculation_entries })
  }
  if (typeof data.deleted_calculation_entries_by_app === 'number') {
    summaryItems.push({ label: 'Calculation entries by app', value: data.deleted_calculation_entries_by_app })
  }
  if (typeof data.deleted_calculation_entries_by_item === 'number') {
    summaryItems.push({ label: 'Calculation entries by item', value: data.deleted_calculation_entries_by_item })
  }
  if (typeof data.deleted_estimation_items === 'number') {
    summaryItems.push({ label: 'Estimation items', value: data.deleted_estimation_items })
  }
  if (typeof data.deleted_estimations === 'number') {
    summaryItems.push({ label: 'Estimations', value: data.deleted_estimations })
  }
  if (typeof data.deleted_ornaments === 'number') {
    summaryItems.push({ label: 'Ornament rows', value: data.deleted_ornaments })
  }
  if (typeof data.invoice_value === 'number') {
    summaryItems.push({ label: 'Invoice value', value: formatCurrency(data.invoice_value) })
  }
  if (typeof data.settlement_value === 'number') {
    summaryItems.push({ label: 'Settlement value', value: formatCurrency(data.settlement_value) })
  }
  if (typeof data.transaction_value === 'number') {
    summaryItems.push({ label: 'Transaction value', value: formatCurrency(data.transaction_value) })
  }

  if (summaryItems.length) {
    sections.push({
      title: 'Quick summary',
      items: summaryItems.map((item) => `${item.label}: ${item.value}`)
    })
  }

  if (Array.isArray(data.application_numbers) && data.application_numbers.length) {
    sections.push({
      title: 'Application numbers',
      items: data.application_numbers.map((item) => `• ${item}`)
    })
  }

  if (Array.isArray(data.ornaments) && data.ornaments.length) {
    sections.push({
      title: 'Ornaments',
      items: data.ornaments.map((item) => `• ${item.name}${item.quantity ? ` ×${item.quantity}` : ''}${item.weight_gms ? ` • ${item.weight_gms} g` : ''}`)
    })
  }

  if (Array.isArray(data.pledges) && data.pledges.length) {
    sections.push({
      title: 'Pledges / pledge-release',
      items: data.pledges.map((p) => `• Pledge #${p.pledge_id} — ${p.pledger_name || 'Unknown'}${p.financier_name ? ` — ${p.financier_name}` : ''} — Principal: ${formatCurrency(p.principal_amount)}${typeof p.total_due === 'number' ? ` • Due: ${formatCurrency(p.total_due)}` : ''}`)
    })
  }

  if (Array.isArray(data.invoice_numbers) && data.invoice_numbers.length) {
    sections.push({
      title: 'Invoice numbers',
      items: data.invoice_numbers.map((item) => `• ${item}`)
    })
  }

  if (Array.isArray(data.invoice_items) && data.invoice_items.length) {
    sections.push({
      title: 'Invoice items',
      items: data.invoice_items.map((item) => `• ${item.name} — ${formatCurrency(item.amount)}`)
    })
  }

  if (Array.isArray(data.transaction_items) && data.transaction_items.length) {
    sections.push({
      title: 'Transaction items',
      items: data.transaction_items.map((item) => `• ${item.name} — ${formatCurrency(item.amount)}`)
    })
  }

  if (Array.isArray(data.settlements) && data.settlements.length) {
    sections.push({
      title: 'Payments / settlements',
      items: data.settlements.map((item) => `• ${item.mode || 'Payment'} — ${formatCurrency(item.amount)}`)
    })
  }

  return sections.length ? sections : [{ title: 'Delete impact', items: ['No preview data available.'] }]
}

export default function DeleteSection() {
  const [mobile, setMobile] = useState('')
  const [selectedAction, setSelectedAction] = useState('applications')
  const [statusMessage, setStatusMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [previewResult, setPreviewResult] = useState(null)
  const [result, setResult] = useState(null)
  const [showRawJson, setShowRawJson] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  useEffect(() => {
    setPreviewResult(null)
    setStatusMessage('')
    setErrorMessage('')
    setResult(null)
  }, [selectedAction])

  const validateMobile = (value) => {
    const normalized = value.trim()
    return /^[0-9]{10}$/.test(normalized)
  }

  const loadPreview = async (actionKey) => {
    const normalizedMobile = mobile.trim()
    setStatusMessage('')
    setErrorMessage('')

    if (!normalizedMobile) {
      setErrorMessage('Customer mobile number is required.')
      return
    }

    if (!validateMobile(normalizedMobile)) {
      setErrorMessage('Please enter a valid 10-digit mobile number.')
      return
    }

    setIsLoading(true)
    try {
      let response
      switch (actionKey) {
        case 'applications':
          response = await deletionsAPI.previewApplications(normalizedMobile)
          break
        case 'payments':
          response = await deletionsAPI.previewPayments(normalizedMobile)
          break
        case 'invoices':
          response = await deletionsAPI.previewInvoices(normalizedMobile)
          break
        case 'transactions':
          response = await deletionsAPI.previewTransactions(normalizedMobile)
          break
        case 'all':
          response = await deletionsAPI.previewAll(normalizedMobile)
          break
        default:
          throw new Error('Unknown action')
      }

      setPreviewResult(response.data)
      setResult(null)
      setStatusMessage(`Showing what ${actionDisplay[actionKey].toLowerCase()} will delete.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Operation failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    const normalizedMobile = mobile.trim()
    setStatusMessage('')
    setErrorMessage('')

    if (!normalizedMobile) {
      setErrorMessage('Customer mobile number is required.')
      return
    }

    if (!validateMobile(normalizedMobile)) {
      setErrorMessage('Please enter a valid 10-digit mobile number.')
      return
    }

    setIsLoading(true)
    try {
      let response
      switch (selectedAction) {
        case 'applications':
          response = await deletionsAPI.deleteApplications(normalizedMobile)
          break
        case 'payments':
          response = await deletionsAPI.deletePayments(normalizedMobile)
          break
        case 'invoices':
          response = await deletionsAPI.deleteInvoices(normalizedMobile)
          break
        case 'transactions':
          response = await deletionsAPI.deleteTransactions(normalizedMobile)
          break
        case 'all':
          response = await deletionsAPI.deleteAll(normalizedMobile)
          break
        default:
          throw new Error('Unknown action')
      }

      setResult(response.data)
      setPreviewResult(null)
      setStatusMessage(`${actionDisplay[selectedAction]} deletion completed successfully.`)
    } catch (err) {
      console.error(err)
      setErrorMessage(err.response?.data?.detail || err.message || 'Delete action failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-3xl shadow-lg p-8 border border-amber-100">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div>
            <h2 className="text-3xl font-bold text-gray-900">Deletion Center</h2>
            <p className="text-sm text-gray-500 mt-2 max-w-2xl">
              Only Vinay can access this section. Choose a mobile, preview the records that will be removed, then confirm to proceed.
            </p>
          </div>
          <div className="flex-1 md:max-w-xs">
            <label className="block text-sm font-semibold text-gray-700 mb-2">Customer Mobile</label>
            <div className="relative">
              <div className="absolute left-4 top-1/2 -translate-y-1/2 text-amber-600"><Search size={18} /></div>
              <input
                type="tel"
                value={mobile}
                onChange={(e) => {
                  setMobile(e.target.value)
                  setErrorMessage('')
                  setStatusMessage('')
                  setPreviewResult(null)
                  setResult(null)
                }}
                placeholder="Enter 10-digit mobile"
                maxLength={10}
                className="w-full pl-11 pr-4 py-4 rounded-2xl border border-gray-200 shadow-sm focus:border-amber-400 focus:ring-2 focus:ring-amber-200"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {actionButtons.map((item) => {
          const Icon = item.icon
          const isActive = selectedAction === item.key
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setSelectedAction(item.key)
                loadPreview(item.key)
              }}
              className={`w-full text-left p-6 rounded-3xl border transition-all duration-200 ${isActive ? 'border-amber-400 shadow-lg bg-amber-50' : 'border-gray-200 bg-white hover:border-amber-300 hover:bg-amber-50'}`}
            >
              <div className="flex items-start gap-4">
                <span className="p-3 rounded-2xl bg-amber-100 text-amber-700"><Icon size={22} /></span>
                <div>
                  <p className="text-lg font-semibold text-gray-900">{item.label}</p>
                  <p className="text-sm text-gray-500 mt-2">{item.description}</p>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      <div className="bg-white rounded-3xl shadow-lg p-8 border border-gray-200">
        <div className="grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="text-sm text-gray-500">Selected action</p>
            <h3 className="text-2xl font-semibold text-gray-900 mt-2">{actionDisplay[selectedAction]}</h3>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              disabled={isLoading}
              onClick={() => setShowConfirmModal(true)}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-red-600 px-6 py-4 text-white font-semibold shadow-lg transition-all hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Trash2 size={18} />
              {isLoading ? 'Working...' : `Delete ${actionDisplay[selectedAction]}`}
            </button>
          </div>
        </div>

        {errorMessage && (
          <div className="mt-6 rounded-2xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <strong className="font-semibold">Error:</strong> {errorMessage}
          </div>
        )}

        {statusMessage && (
          <div className="mt-6 rounded-2xl bg-green-50 border border-green-200 p-4 text-sm text-green-700">
            <strong className="font-semibold">{previewResult ? 'Preview:' : 'Success:'}</strong> {statusMessage}
          </div>
        )}

        {previewResult && (
          <div className="mt-6 rounded-3xl bg-slate-950/5 border border-slate-200 p-6">
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <p className="text-sm text-gray-500">Preview details</p>
                <h4 className="text-xl font-semibold text-gray-900">{actionDisplay[selectedAction]} will delete these records</h4>
              </div>
              <span className="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-800">Delete impact</span>
            </div>
            <div className="space-y-4">
              {buildPreviewSections(previewResult).map((section) => (
                <div key={section.title} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <h5 className="text-sm font-semibold uppercase tracking-wide text-gray-600 mb-3">{section.title}</h5>
                  <ul className="space-y-2 text-sm text-slate-700">
                    {section.items.map((item) => (
                      <li key={item} className="leading-6">{item}</li>
                    ))}
                  </ul>
                </div>
              ))}

              <div>
                <button
                  type="button"
                  onClick={() => setShowRawJson((s) => !s)}
                  className="mt-3 inline-flex items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700 border border-slate-200"
                >
                  {showRawJson ? 'Hide raw JSON' : 'Show raw JSON (ids & details)'}
                </button>
                {showRawJson && (
                  <pre className="mt-3 max-h-72 overflow-auto rounded-md border bg-white p-3 text-xs text-slate-800">
                    {JSON.stringify(previewResult, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          </div>
        )}

        {showConfirmModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/40" onClick={() => setShowConfirmModal(false)} />
            <div className="relative z-10 w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
              <h3 className="text-lg font-semibold">Confirm delete — final check</h3>
              <p className="mt-2 text-sm text-slate-600">Please review the preview below. Type <strong>YES</strong> in the box to enable the Delete button.</p>

              <div className="mt-4 max-h-60 overflow-auto rounded-md border bg-slate-50 p-3 text-xs text-slate-800">
                <pre>{JSON.stringify(previewResult || { message: 'No preview loaded' }, null, 2)}</pre>
              </div>

              <div className="mt-4 flex flex-col gap-3">
                <label className="text-sm font-medium">Type <strong>YES</strong> to confirm</label>
                <input
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="Type YES to confirm"
                  className="w-full rounded-lg border px-3 py-2"
                />
                <div className="flex justify-end gap-3">
                  <button type="button" onClick={() => { setShowConfirmModal(false); setConfirmText('') }} className="rounded-lg px-4 py-2 text-sm bg-slate-100">Cancel</button>
                  <button
                    type="button"
                    disabled={confirmText !== 'YES' || isLoading}
                    onClick={async () => {
                      setShowConfirmModal(false)
                      setConfirmText('')
                      await handleDelete()
                    }}
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white disabled:opacity-50"
                  >
                    Delete now
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {result && (
          <div className="mt-6 rounded-3xl bg-slate-950/5 border border-slate-200 p-6">
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <p className="text-sm text-gray-500">Delete result</p>
                <h4 className="text-xl font-semibold text-gray-900">{actionDisplay[selectedAction]} deleted</h4>
              </div>
              <span className="inline-flex items-center rounded-full bg-red-100 px-3 py-1 text-sm font-medium text-red-800">Completed</span>
            </div>
            <pre className="whitespace-pre-wrap text-sm text-slate-700 overflow-x-auto">{JSON.stringify(result, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
