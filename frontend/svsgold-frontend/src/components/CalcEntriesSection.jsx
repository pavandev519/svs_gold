import React, { useEffect, useMemo, useState } from 'react'
import { AlertCircle, BarChart3, Loader, Save } from 'lucide-react'
import { calcEntriesAPI, transactionsAPI } from '../api/api'
import * as XLSX from 'xlsx'

const toDateKey = (value) => {
  if (!value) return ''
  return value.toString().slice(0, 10)
}

const toInputValue = (value) => {
  if (value === null || value === undefined || value === '') return ''
  return value
}

const toNumber = (value) => {
  if (value === '' || value === null || value === undefined) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const formatNumber = (value, digits = 3) => {
  const number = toNumber(value)
  if (number === null) return ''
  return number.toFixed(digits)
}

const purityFactor = (purity) => {
  const number = toNumber(purity)
  if (number === null) return null
  return number > 1 ? number / 100 : number
}

const calculateFineWeight = (weight, purity) => {
  const numericWeight = toNumber(weight)
  const numericPurity = purityFactor(purity)
  if (numericWeight === null || numericPurity === null) return ''
  return numericWeight * numericPurity
}

const calculateDifference = (refineryFineWeight, fineWeight) => {
  const refineryFine = toNumber(refineryFineWeight)
  const fine = toNumber(fineWeight)
  if (refineryFine === null || fine === null) {
    return ''
  }

  return refineryFine - fine
}

const buildCalcKey = (mobile, applicationId, date, invoiceItemId) =>
  `${mobile || ''}::${applicationId || ''}::${toDateKey(date)}::${invoiceItemId || ''}`

const validateManualValues = (values) => {
  const fields = [
    ['cal_wt_after', 'Refinery weight'],
    ['cal_purity_percentage', 'Refinery purity']
  ]

  for (const [key, label] of fields) {
    const rawValue = values[key]
    if (rawValue === '' || rawValue === null || rawValue === undefined) continue

    const value = Number(rawValue)
    if (!Number.isFinite(value)) {
      return `${label} must be a valid number`
    }

    if (value < 0) {
      return `${label} cannot be negative`
    }
  }

  const calcPurity = values.cal_purity_percentage
  if (calcPurity !== '' && calcPurity !== null && calcPurity !== undefined && Number(calcPurity) > 100) {
    return 'Refinery purity cannot be greater than 100'
  }

  return ''
}

export default function CalcEntriesSection() {
  const [transactions, setTransactions] = useState({ invoices: [], invoice_items: [] })
  const [calcEntries, setCalcEntries] = useState([])
  const [manualValues, setManualValues] = useState({})
  const [loading, setLoading] = useState(false)
  const [savingKey, setSavingKey] = useState('')
  const [error, setError] = useState('')
  const [savedKey, setSavedKey] = useState('')
  const [mode, setMode] = useState('single')
  const [mobileInput, setMobileInput] = useState('')
  const [period, setPeriod] = useState('all')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [sortOrder, setSortOrder] = useState('desc')

  const calcEntryByKey = useMemo(() => {
    const map = new Map()
    calcEntries.forEach((entry) => {
      map.set(
        buildCalcKey(entry.mobile, entry.application_id, entry.entry_date, entry.invoice_item_id),
        entry
      )
    })
    return map
  }, [calcEntries])

  const rows = useMemo(() => {
    return (transactions.invoice_items || []).map((item) => {
      const invoice = (transactions.invoices || []).find(
        (inv) => inv.payment_invoice_id === item.payment_invoice_id
      )
      const mobile = invoice?.customer_details?.mobile || invoice?.customer_mobile || ''
      const entryDate = toDateKey(invoice?.invoice_date)
      const applicationId = invoice?.application_id
      const invoiceItemId = item.invoice_item_id
      const rowKey = buildCalcKey(mobile, applicationId, entryDate, invoiceItemId)
      const calcEntry = calcEntryByKey.get(rowKey)

      return {
        rowKey,
        invoice,
        item,
        calcEntry,
        mobile,
        entryDate,
        applicationId,
        invoiceItemId,
        applicationNo: invoice?.application_no || invoice?.application_id || '-',
        invoiceNo: invoice?.invoice_no || invoice?.payment_invoice_id || '-',
        branch: invoice?.application_branch || invoice?.branch || invoice?.place || '-',
        wtBefore: item.weight_before_melting,
        wtAfter: item.weight_after_melting,
        purity: item.purity_after_melting
      }
    })
  }, [transactions, calcEntryByKey])

  const loadData = async () => {
    try {
      setLoading(true)
      setError('')
      const [transactionsResponse, calcEntriesResponse] = await Promise.all([
        transactionsAPI.getAll(mode === 'single' ? mobileInput.trim() : ''),
        calcEntriesAPI.getAll()
      ])
      const nextTransactions = transactionsResponse.data || { invoices: [], invoice_items: [] }
      const nextEntries = calcEntriesResponse.data?.entries || []

      setTransactions(nextTransactions)
      setCalcEntries(nextEntries)

      const nextManualValues = {}
      nextEntries.forEach((entry) => {
        const key = buildCalcKey(entry.mobile, entry.application_id, entry.entry_date, entry.invoice_item_id)
        nextManualValues[key] = {
          cal_wt_after: toInputValue(entry.refinery_weight ?? entry.cal_wt_after),
          cal_purity_percentage: toInputValue(entry.refinery_purity ?? entry.cal_purity_percentage)
        }
      })
      setManualValues(nextManualValues)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load calculated transactions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const filteredRows = useMemo(() => {
    let result = [...rows]

    if (mode === 'single' && mobileInput.trim()) {
      result = result.filter((row) => row.mobile === mobileInput.trim())
    }

    if (period !== 'all') {
      const cutoff = new Date()
      cutoff.setDate(cutoff.getDate() - parseInt(period, 10))
      result = result.filter((row) => {
        if (!row.entryDate) return false
        return new Date(row.entryDate) >= cutoff
      })
    }

    if (fromDate && toDate) {
      const from = new Date(fromDate)
      const to = new Date(toDate)
      result = result.filter((row) => {
        if (!row.entryDate) return false
        const rowDate = new Date(row.entryDate)
        return rowDate >= from && rowDate <= to
      })
    }

    return result.sort((a, b) => {
      const dateA = new Date(a.entryDate || 0).getTime()
      const dateB = new Date(b.entryDate || 0).getTime()
      return sortOrder === 'asc' ? dateA - dateB : dateB - dateA
    })
  }, [rows, mode, mobileInput, period, fromDate, toDate, sortOrder])

  const cumulativeSummary = useMemo(() => {
    const summary = {
      weightAfterMelting: 0,
      purityPercentage: 0,
      fineWeight: 0,
      refineryWeight: 0,
      refineryPurityPercentage: 0,
      refineryFineWeight: 0,
      difference: 0
    }

    if (filteredRows.length === 0) return summary

    filteredRows.forEach((row) => {
      const wtAfter = toNumber(row.wtAfter) || 0
      const purity = toNumber(row.purity) || 0
      const fineWt = calculateFineWeight(row.wtAfter, row.purity) || 0

      const values = manualValues[row.rowKey] || {}
      const refineryWt = toNumber(values.cal_wt_after ?? row.calcEntry?.refinery_weight ?? row.calcEntry?.cal_wt_after) || 0
      const refineryPurity = toNumber(values.cal_purity_percentage ?? row.calcEntry?.refinery_purity ?? row.calcEntry?.cal_purity_percentage) || 0
      const refineryFineWt = calculateFineWeight(refineryWt, refineryPurity) || 0

      summary.weightAfterMelting += wtAfter
      summary.purityPercentage += purity
      summary.fineWeight += fineWt
      summary.refineryWeight += refineryWt
      summary.refineryPurityPercentage += refineryPurity
      summary.refineryFineWeight += refineryFineWt
      summary.difference += calculateDifference(refineryFineWt, fineWt) || 0
    })

    // Average purity percentages
    if (filteredRows.length > 0) {
      summary.purityPercentage = summary.purityPercentage / filteredRows.length
      summary.refineryPurityPercentage = summary.refineryPurityPercentage / filteredRows.length
    }

    return summary
  }, [filteredRows, manualValues])

  const exportExcel = () => {
    if (filteredRows.length === 0) {
      setError('No calculated transactions available to export')
      return
    }

    const exportRows = filteredRows.map((row) => {
      const values = manualValues[row.rowKey] || {}
      const refineryWeight = values.cal_wt_after ?? row.calcEntry?.refinery_weight ?? row.calcEntry?.cal_wt_after ?? ''
      const refineryPurity = values.cal_purity_percentage ?? row.calcEntry?.refinery_purity ?? row.calcEntry?.cal_purity_percentage ?? ''
      const fineWeight = calculateFineWeight(row.wtAfter, row.purity)
      const refineryFineWeight = calculateFineWeight(refineryWeight, refineryPurity)
      const difference = calculateDifference(refineryFineWeight, fineWeight)

      return {
        Application_Number: row.applicationNo || '',
        Invoice_Number: row.invoiceNo || '',
        Date: row.entryDate || '',
        Branch: row.branch || '',
        Weight_After_Melting: row.wtAfter || '',
        Purity: row.purity || '',
        Fine_Weight: formatNumber(fineWeight),
        Refinery_Weight: refineryWeight,
        Refinery_Purity: refineryPurity,
        Refinery_Fine_Weight: formatNumber(refineryFineWeight),
        Difference: formatNumber(difference)
      }
    })

    const ws = XLSX.utils.json_to_sheet(exportRows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Calculated Transactions')
    const dateSuffix = new Date().toISOString().slice(0, 10)
    XLSX.writeFile(wb, `calculated-transactions-${dateSuffix}.xlsx`)
  }

  const handleManualChange = (rowKey, field, value) => {
    setManualValues((prev) => ({
      ...prev,
      [rowKey]: {
        ...(prev[rowKey] || {}),
        [field]: value
      }
    }))
  }

  const parseOptionalNumber = (value) => {
    if (value === '' || value === null || value === undefined) return null
    return parseFloat(value)
  }

  const saveRow = async (row) => {
    if (!row.mobile || !row.applicationId || !row.entryDate) {
      setError('Missing phone, application, or date for this transaction row')
      return
    }

    const values = manualValues[row.rowKey] || {}
    const validationError = validateManualValues(values)
    if (validationError) {
      setError(validationError)
      return
    }

    const payload = {
      application_number: row.applicationNo,
      invoice_number: row.invoiceNo,
      wt_after: parseOptionalNumber(row.wtAfter) || 0,
      purity_percentage: parseOptionalNumber(row.purity) || 0,
      cal_wt_before: null,
      cal_wt_after: parseOptionalNumber(values.cal_wt_after),
      cal_purity_percentage: parseOptionalNumber(values.cal_purity_percentage)
    }

    try {
      setSavingKey(row.rowKey)
      setError('')

      const response = row.calcEntry?.calc_entry_id
        ? await calcEntriesAPI.updateEntry(row.calcEntry.calc_entry_id, payload, row.mobile)
        : await calcEntriesAPI.createEntry({
            mobile: row.mobile,
            application_id: row.applicationId,
            invoice_item_id: row.invoiceItemId,
            application_number: row.applicationNo,
            invoice_number: row.invoiceNo,
            entry_date: row.entryDate,
            wt_before: parseOptionalNumber(row.wtBefore) || 0,
            wt_after: parseOptionalNumber(row.wtAfter) || 0,
            purity_percentage: parseOptionalNumber(row.purity) || 0,
            ...payload
          })

      const savedEntry = response.data
      setCalcEntries((prev) => {
        const key = buildCalcKey(savedEntry.mobile, savedEntry.application_id, savedEntry.entry_date, savedEntry.invoice_item_id)
        const filtered = prev.filter(
          (entry) => buildCalcKey(entry.mobile, entry.application_id, entry.entry_date, entry.invoice_item_id) !== key
        )
        return [savedEntry, ...filtered]
      })
      setSavedKey(row.rowKey)
      window.setTimeout(() => setSavedKey(''), 2500)
    } catch (err) {
      setError(err.response?.data?.msg || err.response?.data?.detail || 'Failed to save calculated transaction')
    } finally {
      setSavingKey('')
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] px-6 py-5 rounded-3xl border border-[#D6B36A] shadow-xl">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-wide">
              Calculated Transactions
            </h2>
            <p className="text-amber-100 text-sm mt-1">
              Transaction weights with manual calculation fields
            </p>
          </div>
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl bg-white/15 px-4 py-2 text-sm font-semibold text-white border border-white/20 hover:bg-white/25 disabled:opacity-60"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <BarChart3 size={16} />}
            Load
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 border-2 border-red-200 rounded-xl">
          <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
          <span className="text-sm text-red-700">{error}</span>
        </div>
      )}

      <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5 shadow-sm">
        <h3 className="font-semibold text-gray-800 text-sm mb-5">
          Transaction Filters
        </h3>

        <div className="grid lg:grid-cols-12 gap-5 items-start">
          <div className="lg:col-span-9">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {mode === 'single' && (
                <div>
                  <label className="text-xs font-medium text-gray-600 mb-2 block">
                    Phone Number
                  </label>
                  <input
                    value={mobileInput}
                    onChange={(e) => setMobileInput(e.target.value.replace(/[^0-9]/g, '').slice(0, 10))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') loadData()
                    }}
                    placeholder="Mobile"
                    className="w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 text-sm outline-none focus:border-[#B67D22]"
                  />
                </div>
              )}

              <div>
                <label className="text-xs font-medium text-gray-600 mb-2 block">
                  From Date
                </label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => {
                    setPeriod('all')
                    setFromDate(e.target.value)
                  }}
                  className="w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 text-sm outline-none focus:border-[#B67D22]"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-600 mb-2 block">
                  To Date
                </label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => {
                    setPeriod('all')
                    setToDate(e.target.value)
                  }}
                  className="w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 text-sm outline-none focus:border-[#B67D22]"
                />
              </div>
            </div>

            <div className="mt-5">
              <label className="text-xs font-medium text-gray-600 mb-2 block">
                Period
              </label>
              <div className="flex gap-2 flex-wrap">
                {['7', '14', '30', 'all'].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setPeriod(value)
                      setFromDate('')
                      setToDate('')
                    }}
                    className={`px-5 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                      period === value
                        ? 'text-white border-transparent shadow-md'
                        : 'bg-white text-gray-700 border-[#D8C08A]'
                    }`}
                    style={
                      period === value
                        ? { background: 'linear-gradient(135deg,#7A4E0B,#A9741F,#D4A437)' }
                        : {}
                    }
                  >
                    {value === 'all' ? 'All' : `${value}d`}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="lg:col-span-3 flex justify-end">
            <div className="w-full max-w-[280px] space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setMode('single')}
                  className={`py-3 rounded-xl font-medium border text-sm ${
                    mode === 'single'
                      ? 'text-white border-transparent shadow-md'
                      : 'bg-white text-gray-700 border-[#D8C08A]'
                  }`}
                  style={mode === 'single' ? { background: 'linear-gradient(135deg,#7A4E0B,#A9741F,#D4A437)' } : {}}
                >
                  Single
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setMode('all')
                    setMobileInput('')
                  }}
                  className={`py-3 rounded-xl font-medium border text-sm ${
                    mode === 'all'
                      ? 'text-white border-transparent shadow-md'
                      : 'bg-white text-gray-700 border-[#D8C08A]'
                  }`}
                  style={mode === 'all' ? { background: 'linear-gradient(135deg,#7A4E0B,#A9741F,#D4A437)' } : {}}
                >
                  All
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSortOrder('asc')}
                  className={`py-3 rounded-xl font-medium border text-sm ${
                    sortOrder === 'asc'
                      ? 'text-white border-transparent shadow-md'
                      : 'bg-white text-gray-700 border-[#D8C08A]'
                  }`}
                  style={sortOrder === 'asc' ? { background: 'linear-gradient(135deg,#7A4E0B,#A9741F,#D4A437)' } : {}}
                >
                  ↑ Asc
                </button>

                <button
                  type="button"
                  onClick={() => setSortOrder('desc')}
                  className={`py-3 rounded-xl font-medium border text-sm ${
                    sortOrder === 'desc'
                      ? 'text-white border-transparent shadow-md'
                      : 'bg-white text-gray-700 border-[#D8C08A]'
                  }`}
                  style={sortOrder === 'desc' ? { background: 'linear-gradient(135deg,#7A4E0B,#A9741F,#D4A437)' } : {}}
                >
                  ↓ Desc
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={loadData}
                  className="bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] text-white font-medium rounded-xl py-3 text-sm"
                >
                  Load
                </button>

                <button
                  type="button"
                  onClick={exportExcel}
                  className="border border-[#D8C08A] rounded-xl py-3 text-sm font-medium text-gray-700 hover:bg-[#FFF8E8]"
                >
                  Export
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Cumulative Summary Container */}
      <div className="mt-6 bg-white rounded-3xl border border-[#E7D3A4] shadow-sm p-6">
        <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-amber-700" />
          Refinery Summary
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <p className="text-xs text-gray-600 mb-1 font-medium">Weight After Melting</p>
            <p className="text-xl font-bold text-amber-900">{formatNumber(cumulativeSummary.weightAfterMelting)}</p>
          </div>
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <p className="text-xs text-gray-600 mb-1 font-medium">Fine Wt</p>
            <p className="text-xl font-bold text-amber-900">{formatNumber(cumulativeSummary.fineWeight)}</p>
          </div>
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <p className="text-xs text-gray-600 mb-1 font-medium">Refinery Weight</p>
            <p className="text-xl font-bold text-amber-900">{formatNumber(cumulativeSummary.refineryWeight)}</p>
          </div>
          <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
            <p className="text-xs text-gray-600 mb-1 font-medium">Refinery Fine Wt</p>
            <p className="text-xl font-bold text-blue-900">{formatNumber(cumulativeSummary.refineryFineWeight)}</p>
          </div>
          <div className="bg-indigo-50 rounded-xl p-4 border border-indigo-200">
            <p className="text-xs text-gray-600 mb-1 font-medium">Difference</p>
            <p className="text-xl font-bold text-indigo-900">{formatNumber(cumulativeSummary.difference)}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-3xl border border-[#E7D3A4] shadow-sm overflow-auto max-h-[68vh]">
        <table className="min-w-[1320px] w-full text-sm divide-y divide-gray-200">
          <thead className="bg-[#B68A2E] text-white">
            <tr>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Application Number</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Invoice Number</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Date</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Branch</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Weight After Melting</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Purity %</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Fine Wt</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Refinery Weight</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Refinery Purity %</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Refinery Fine Wt</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Difference</th>
              <th className="sticky top-0 z-10 px-4 py-3 text-left text-xs uppercase tracking-[0.12em] bg-[#B68A2E]">Action</th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {loading ? (
              <tr>
                <td colSpan={12} className="px-4 py-10 text-center text-gray-500">
                  Loading calculated transactions...
                </td>
              </tr>
            ) : filteredRows.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-4 py-10 text-center text-gray-500">
                  No transaction records found.
                </td>
              </tr>
            ) : (
              filteredRows.map((row) => {
                const values = manualValues[row.rowKey] || {
                  cal_wt_after: toInputValue(row.calcEntry?.refinery_weight ?? row.calcEntry?.cal_wt_after),
                  cal_purity_percentage: toInputValue(row.calcEntry?.refinery_purity ?? row.calcEntry?.cal_purity_percentage)
                }
                const fineWeight = calculateFineWeight(row.wtAfter, row.purity)
                const refineryFineWeight = calculateFineWeight(values.cal_wt_after, values.cal_purity_percentage)
                const difference = calculateDifference(refineryFineWeight, fineWeight)

                return (
                  <tr key={`${row.item.invoice_item_id || row.rowKey}`} className="border-b even:bg-gray-50 hover:bg-gray-100">
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.applicationNo}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.invoiceNo}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.entryDate || '-'}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.branch || '-'}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{formatNumber(row.wtAfter) || '-'}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-700">{row.purity ?? '-'}</td>
                    <td className="px-4 py-3 whitespace-nowrap font-semibold text-gray-800">{formatNumber(fineWeight) || '-'}</td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        inputMode="decimal"
                        min="0"
                        value={values.cal_wt_after ?? ''}
                        onChange={(e) => {
                          let val = e.target.value.replace(/[^0-9.]/g, '')
                          const parts = val.split('.')
                          if (parts.length > 2) val = parts[0] + '.' + parts.slice(1).join('')
                          if (parts[1] && parts[1].length > 3) val = parts[0] + '.' + parts[1].slice(0, 3)
                          handleManualChange(row.rowKey, 'cal_wt_after', val)
                        }}
                        className="w-32 rounded-xl border border-[#D8C08A] bg-white px-3 py-2 outline-none focus:border-[#B67D22]"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        inputMode="decimal"
                        min="0"
                        max="100"
                        value={values.cal_purity_percentage ?? ''}
                        onChange={(e) => {
                          let val = e.target.value.replace(/[^0-9.]/g, '')
                          const parts = val.split('.')
                          if (parts.length > 2) val = parts[0] + '.' + parts.slice(1).join('')
                          if (parts[1] && parts[1].length > 3) val = parts[0] + '.' + parts[1].slice(0, 3)
                          handleManualChange(row.rowKey, 'cal_purity_percentage', val)
                        }}
                        className="w-32 rounded-xl border border-[#D8C08A] bg-white px-3 py-2 outline-none focus:border-[#B67D22]"
                      />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap font-semibold text-gray-800">{formatNumber(refineryFineWeight) || '-'}</td>
                    <td className="px-4 py-3 whitespace-nowrap font-semibold text-gray-800">{formatNumber(difference) || '-'}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => saveRow(row)}
                        disabled={savingKey === row.rowKey}
                        className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] px-4 py-2 text-sm font-semibold text-white shadow disabled:opacity-60"
                      >
                        {savingKey === row.rowKey ? <Loader size={14} className="animate-spin" /> : <Save size={14} />}
                        Save
                      </button>
                        {savedKey === row.rowKey && (
                          <span className="whitespace-nowrap text-xs font-semibold text-green-700">
                            Saved successfully
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
