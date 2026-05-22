import React, { useEffect, useRef, useState } from 'react'
import {
  Save,
  Loader2,
  CheckCircle2,
  User,
  Phone,
  Wallet,
  CalendarDays,
  FileText
} from 'lucide-react'
import { enquiriesAPI, applicationsAPI } from '../api/api'
import * as XLSX from 'xlsx'

const enquiryTypes = [
  'Sell Gold',
  'Pledge Gold'
]

const salutations = [
  'Mr',
  'Mrs',
  'Ms',
  'Dr',
  'Prof',
  'Other'
]

const sourceOptions = [
  'Walk-in',
  'Phone',
  'WhatsApp',
  'Web',
  'Referral',
  'Other'
]

const defaultOrnamentTypes = [
  'Ring',
  'Chain',
  'Bangle',
  'Bracelet',
  'Earrings',
  'Pendant',
  'Other'
]

const priorityOptions = ['Low', 'Medium', 'High']
const leadStateOptions = ['Qualified', 'Disqualified']
const leadStatusOptions = ['Answered', 'Not Answered']
const leadStageOptions = ['Enquiry', 'Gold Loan', 'Already sold', 'Processing fee','Non local','Not interested','Follow-up later','Junk','Converted','Others']

const initialForm = {
  salutation: 'Mr',
  name: '',
  mobile: '',
  email: '',
  branch: '',
  enquiry_type: 'Sell Gold',
  product_interest: '',
  source: 'Walk-in',
  ornament_type: 'Ring',
  quantity: '',
  gross_weight_gms: '',
  net_weight_gms: '',
  purity_percentage: '',
  rate: '',
  pledge_amount: '',
  financier_name: '',
  financier_branch: '',
  lead_state: 'New',
  lead_status: 'Open',
  lead_stage: 'Inquiry',
  follow_up_date: '',
  priority: 'Medium',
  remarks: ''
}

export default function Enquiry() {
  const [form, setForm] = useState(initialForm)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const [recentEnquiries, setRecentEnquiries] = useState([])
  const [loadingRecent, setLoadingRecent] = useState(false)
  const [branches, setBranches] = useState([])
  const [ornamentTypes, setOrnamentTypes] = useState(defaultOrnamentTypes)
  const [pastFilter, setPastFilter] = useState({
    date_from: '',
    date_to: '',
    enquiry_type: '',
    branch: '',
    mobile: '',
    follow_up_date: '',
    lead_state: '',
    lead_status: '',
    lead_stage: '',
    sort_order: 'desc'
  })
  const [pastEnquiries, setPastEnquiries] = useState([])
  const [loadingPast, setLoadingPast] = useState(false)
  const [pastError, setPastError] = useState('')

  const expectedRate = (() => {
    const netWeight = parseFloat(form.net_weight_gms) || 0
    const purity = parseFloat(form.purity_percentage) || 0
    const dayRate = parseFloat(form.rate) || 0
    if (!netWeight || !purity || !dayRate) return ''
    return (netWeight * (purity / 100) * dayRate).toFixed(2)
  })()

  useEffect(() => {
    const loadBranches = async () => {
      try {
        const response = await applicationsAPI.getBranches()
        setBranches(response?.data?.branches || [])
      } catch (err) {
        setBranches([])
      }
    }

    const loadGoldItems = async () => {
      try {
        const response = await applicationsAPI.getGoldItems()
        const items = response?.data?.gold_items || []
        if (items.length > 0) {
          const names = items.map((item) => item.name)
          setOrnamentTypes(names)
          setForm((prev) => ({
            ...prev,
            ornament_type: names.includes(prev.ornament_type)
              ? prev.ornament_type
              : names[0]
          }))
        }
      } catch (err) {
        setOrnamentTypes(defaultOrnamentTypes)
      }
    }

    loadBranches()
    loadGoldItems()
  }, [])

  const handleChange = (key, value) => {
    setForm(prev => ({
      ...prev,
      [key]: value
    }))

    if (key === 'mobile' && value.length >= 10) {
      loadRecentEnquiries(value)
    }
  }

  const loadRecentEnquiries = async (mobile) => {
    try {
      setLoadingRecent(true)

      const response =
        await enquiriesAPI.getByMobile(mobile)

      setRecentEnquiries(
        response?.data?.enquiries || []
      )
    } catch (err) {
      setRecentEnquiries([])
    } finally {
      setLoadingRecent(false)
    }
  }

  const handlePastFilterChange = (key, value) => {
    setPastFilter((prev) => ({
      ...prev,
      [key]: value
    }))
  }

  const loadPastEnquiries = async () => {
    try {
      setLoadingPast(true)
      setPastError('')

      const response = await enquiriesAPI.getByDate({
        dateFrom: pastFilter.date_from,
        dateTo: pastFilter.date_to,
        enquiryType: pastFilter.enquiry_type,
        branch: pastFilter.branch,
        mobile: pastFilter.mobile,
        followUpDate: pastFilter.follow_up_date,
        leadState: pastFilter.lead_state,
        leadStatus: pastFilter.lead_status,
        leadStage: pastFilter.lead_stage,
        sortOrder: pastFilter.sort_order
      })

      setPastEnquiries(response?.data?.enquiries || [])
    } catch (err) {
      setPastEnquiries([])
      setPastError(
        err.response?.data?.detail ||
          'Unable to fetch past enquiries'
      )
    } finally {
      setLoadingPast(false)
    }
  }

  const exportPastEnquiries = () => {
    if (pastEnquiries.length === 0) {
      setPastError('No results available to export')
      return
    }

    const rows = pastEnquiries.map((item) => ({
      Date: formatDateTime(item.created_at),
      Customer: item.name || '',
      Mobile: item.mobile || '',
      Category: item.enquiry_type || '',
      Lead_State: item.lead_state || '',
      Lead_Status: item.lead_status || '',
      Lead_Stage: item.lead_stage || '',
      Follow_Up_Date: item.follow_up_date || '',
      Branch: item.branch || '',
      Pledge_Amount: item.pledge_amount || '',
      Financier_Name: item.financier_name || '',
      Financier_Branch: item.financier_branch || ''
    }))

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Past Enquiries')
    const dateSuffix = new Date().toISOString().slice(0, 10)
    XLSX.writeFile(wb, `past-enquiries-${dateSuffix}.xlsx`)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    setError('')
    setSuccess('')

    if (!form.name.trim()) {
      setError('Customer name is required')
      return
    }

    if (!form.mobile.trim()) {
      setError('Mobile number is required')
      return
    }

    setSaving(true)

    try {
      const payload = {
        name: form.name,
        mobile: form.mobile,
        email: form.email,
        branch: form.branch,
        enquiry_type: form.enquiry_type,
        product_interest: form.product_interest,
        source: form.source,
        ornament_type: form.ornament_type,
        quantity: form.quantity
          ? parseInt(form.quantity, 10)
          : null,
        expected_amount: expectedRate
          ? parseFloat(expectedRate)
          : form.rate
          ? parseFloat(form.rate)
          : null,
        gold_weight_gms: form.net_weight_gms
          ? parseFloat(form.net_weight_gms)
          : null,
        purity_percentage:
          form.purity_percentage
            ? parseFloat(
                form.purity_percentage
              )
            : null,
        pledge_amount: form.pledge_amount
          ? parseFloat(form.pledge_amount)
          : null,
        financier_name: form.financier_name,
        financier_branch: form.financier_branch,
        lead_state: form.lead_state,
        lead_status: form.lead_status,
        lead_stage: form.lead_stage,
        follow_up_date: form.follow_up_date || null,
        priority: form.priority,
        remarks: form.remarks
      }

      const response =
        await enquiriesAPI.createEnquiry(
          payload
        )

      setSuccess(
        `Enquiry saved successfully (ID: ${response.data.enquiry_id})`
      )

      setForm({
        ...initialForm,
        mobile: form.mobile
      })

      loadRecentEnquiries(form.mobile)
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Unable to save enquiry'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 lg:p-6 bg-[#F8F6F1] min-h-screen">
      <div className="bg-white rounded-3xl shadow-xl border border-[#E5D2A0] overflow-hidden">

        {/* HEADER */}
        <div className="bg-gradient-to-r from-[#7A4E0B] via-[#A9741F] to-[#D4A437] px-6 py-5 border-b border-[#D6B36A]">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white tracking-wide">
                Enquiry Form
              </h2>

              <p className="text-amber-100 text-sm mt-1">
                Customer enquiry & lead management
              </p>
            </div>

            <div className="hidden md:flex items-center gap-2 bg-white/10 px-4 py-2 rounded-xl border border-white/20">
              <FileText
                size={18}
                className="text-amber-200"
              />

              <span className="text-white text-sm font-medium">
                CRM Enquiry
              </span>
            </div>
          </div>
        </div>

        <div className="p-5 space-y-6">
          <div className="bg-white border border-[#E5D2A0] rounded-2xl p-5 shadow-sm">
            <h3 className="font-bold text-gray-800 mb-4">
              Past Enquiries
            </h3>

            <div className="grid md:grid-cols-2 xl:grid-cols-5 gap-4">
              <InputField
                label="Phone Number"
                value={pastFilter.mobile}
                onChange={(v) =>
                  handlePastFilterChange('mobile', v)
                }
              />

              <InputField
                type="date"
                label="From Date"
                value={pastFilter.date_from}
                onChange={(v) =>
                  handlePastFilterChange('date_from', v)
                }
              />

              <InputField
                type="date"
                label="To Date"
                value={pastFilter.date_to}
                onChange={(v) =>
                  handlePastFilterChange('date_to', v)
                }
              />

              <SelectField
                label="Category"
                value={pastFilter.enquiry_type}
                options={enquiryTypes}
                placeholder="All categories"
                onChange={(v) =>
                  handlePastFilterChange('enquiry_type', v)
                }
              />

              <SelectField
                label="Branch"
                value={pastFilter.branch}
                options={branches.map((branch) => branch.branch_name)}
                placeholder="All branches"
                onChange={(v) =>
                  handlePastFilterChange('branch', v)
                }
              />

              <InputField
                type="date"
                label="Follow-up Date"
                value={pastFilter.follow_up_date}
                onChange={(v) =>
                  handlePastFilterChange('follow_up_date', v)
                }
              />

              <SelectField
                label="Lead State"
                value={pastFilter.lead_state}
                options={leadStateOptions}
                placeholder="All lead states"
                onChange={(v) =>
                  handlePastFilterChange('lead_state', v)
                }
              />

              <SelectField
                label="Lead Status"
                value={pastFilter.lead_status}
                options={leadStatusOptions}
                placeholder="All lead statuses"
                onChange={(v) =>
                  handlePastFilterChange('lead_status', v)
                }
              />

              <SelectField
                label="Lead Stage"
                value={pastFilter.lead_stage}
                options={leadStageOptions}
                placeholder="All lead stages"
                onChange={(v) =>
                  handlePastFilterChange('lead_stage', v)
                }
              />

              <SelectField
                label="Sort Order"
                value={pastFilter.sort_order}
                options={['desc', 'asc']}
                onChange={(v) =>
                  handlePastFilterChange('sort_order', v)
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={loadPastEnquiries}
                disabled={loadingPast}
                className="bg-gradient-to-r from-[#8B5E12] via-[#B67D22] to-[#D4A437] hover:opacity-95 transition-all text-white font-semibold rounded-2xl px-5 py-3 flex items-center gap-2 shadow-lg"
              >
                {loadingPast && (
                  <Loader2
                    size={16}
                    className="animate-spin"
                  />
                )}
                {loadingPast
                  ? 'Fetching...'
                  : 'Fetch Past Enquiries'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setPastFilter({
                    date_from: '',
                    date_to: '',
                    enquiry_type: '',
                    branch: '',
                    mobile: '',
                    follow_up_date: '',
                    lead_state: '',
                    lead_status: '',
                    lead_stage: '',
                    sort_order: 'desc'
                  })
                  setPastEnquiries([])
                  setPastError('')
                }}
                className="rounded-2xl border border-[#D8C08A] px-5 py-3 font-semibold text-gray-700 hover:bg-[#FFF8E8] transition-all"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={exportPastEnquiries}
                className="rounded-2xl border border-[#D8C08A] px-5 py-3 font-semibold text-gray-700 hover:bg-[#FFF8E8] transition-all"
              >
                Export Results
              </button>
            </div>

            {pastError && (
              <div className="mt-4 bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 text-sm">
                {pastError}
              </div>
            )}

            <div className="mt-5 overflow-x-auto rounded-xl border border-[#E8D5A8]">
              <table className="w-full min-w-[840px] text-sm">
                <thead className="bg-[#FFF4D6]">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Date</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Customer</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Mobile</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Category</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Follow-up Date</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead State</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead Status</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Lead Stage</th>
                    <th className="px-4 py-3 text-left font-semibold text-[#8B5E12]">Branch</th>
                  </tr>
                </thead>

                <tbody>
                  {pastEnquiries.length > 0 ? (
                    pastEnquiries.map((item) => (
                      <tr
                        key={item.enquiry_id}
                        className="border-t border-[#E8D5A8] bg-[#FFFDF8]"
                      >
                        <td className="px-4 py-3 text-gray-700">
                          {formatDateTime(item.created_at)}
                        </td>
                        <td className="px-4 py-3 text-gray-800">
                          {item.name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.mobile || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.enquiry_type || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.follow_up_date || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_state || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_status || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.lead_stage || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {item.branch || '—'}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                          colSpan="9"
                          className="px-4 py-6 text-center text-gray-500 bg-[#FFFDF8]"
                        >
                        {loadingPast
                          ? 'Loading past enquiries...'
                          : 'No past enquiries found'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <form
            onSubmit={handleSubmit}
            className="grid xl:grid-cols-[minmax(0,1.8fr)_340px] gap-6"
          >

          {/* LEFT SECTION */}
          <div className="space-y-5">

            {/* CUSTOMER INFO */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <User
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Customer Information
                </h3>
              </div>

              <div className="grid md:grid-cols-2 gap-4">

                <SelectField
                  label="Salutation"
                  value={form.salutation}
                  options={salutations}
                  onChange={(v) =>
                    handleChange('salutation', v)
                  }
                />

                <InputField
                  label="Customer Name *"
                  value={form.name}
                  onChange={(v) =>
                    handleChange('name', v)
                  }
                />

                <InputField
                  label="Mobile Number *"
                  value={form.mobile}
                  onChange={(v) =>
                    handleChange('mobile', v)
                  }
                />

                <InputField
                  label="Email"
                  value={form.email}
                  onChange={(v) =>
                    handleChange('email', v)
                  }
                />

                <SelectField
                  label="Branch"
                  value={form.branch}
                  options={branches.map((branch) => branch.branch_name)}
                  placeholder="Select branch"
                  onChange={(v) =>
                    handleChange('branch', v)
                  }
                />
              </div>
            </div>

            {/* ENQUIRY DETAILS */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Phone
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Enquiry Details
                </h3>
              </div>

              <div className="grid md:grid-cols-2 gap-4">

                <SelectField
                  label="Enquiry Type"
                  value={form.enquiry_type}
                  options={enquiryTypes}
                  onChange={(v) =>
                    handleChange(
                      'enquiry_type',
                      v
                    )
                  }
                />

                {/* <InputField
                  label="Product / Service"
                  value={form.product_interest}
                  onChange={(v) =>
                    handleChange(
                      'product_interest',
                      v
                    )
                  }
                /> */}

                <SelectField
                  label="Source"
                  value={form.source}
                  options={sourceOptions}
                  onChange={(v) =>
                    handleChange('source', v)
                  }
                />

                <SelectField
                  label="Priority"
                  value={form.priority}
                  options={priorityOptions}
                  onChange={(v) =>
                    handleChange('priority', v)
                  }
                />
              </div>
            </div>

            {/* GOLD DETAILS */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Wallet
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Gold Details
                </h3>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                <SelectField
                  label="Ornament Type"
                  value={form.ornament_type}
                  options={ornamentTypes}
                  onChange={(v) =>
                    handleChange('ornament_type', v)
                  }
                />

                <InputField
                  type="number"
                  label="Quantity"
                  value={form.quantity}
                  onChange={(v) =>
                    handleChange('quantity', v)
                  }
                />

                <InputField
                  type="number"
                  label="Gross Weight (g)"
                  value={form.gross_weight_gms}
                  onChange={(v) =>
                    handleChange(
                      'gross_weight_gms',
                      v
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Net Weight (g)"
                  value={form.net_weight_gms}
                  onChange={(v) =>
                    handleChange(
                      'net_weight_gms',
                      v
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Purity (%)"
                  value={form.purity_percentage}
                  onChange={(v) =>
                    handleChange(
                      'purity_percentage',
                      v
                    )
                  }
                />

                <InputField
                  type="number"
                  label="Day Rate"
                  value={form.rate}
                  onChange={(v) =>
                    handleChange('rate', v)
                  }
                />
              </div>

              <div className="mt-4">
                <InputField
                  type="text"
                  label="Expected Rate"
                  value={expectedRate}
                  readOnly
                />
              </div>

              {form.enquiry_type === 'Pledge Gold' && (
                <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5 mt-5">
                  <div className="flex items-center gap-2 mb-4">
                    <Wallet
                      size={18}
                      className="text-[#A9741F]"
                    />

                    <h3 className="font-semibold text-gray-800">
                      Pledge Details
                    </h3>
                  </div>

                  <div className="grid md:grid-cols-3 gap-4">
                    <InputField
                      type="number"
                      label="Pledge Amount"
                      value={form.pledge_amount}
                      onChange={(v) =>
                        handleChange('pledge_amount', v)
                      }
                    />

                    <InputField
                      label="Financier Name"
                      value={form.financier_name}
                      onChange={(v) =>
                        handleChange('financier_name', v)
                      }
                    />

                    <InputField
                      label="Financier Branch"
                      value={form.financier_branch}
                      onChange={(v) =>
                        handleChange('financier_branch', v)
                      }
                    />
                  </div>
                </div>
              )}

              <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5 mt-5">
                <div className="flex items-center gap-2 mb-4">
                  <FileText
                    size={18}
                    className="text-[#A9741F]"
                  />

                  <h3 className="font-semibold text-gray-800">
                    Leads
                  </h3>
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <SelectField
                    label="Lead State"
                    value={form.lead_state}
                    options={leadStateOptions}
                    onChange={(v) =>
                      handleChange('lead_state', v)
                    }
                  />

                  <SelectField
                    label="Lead Status"
                    value={form.lead_status}
                    options={leadStatusOptions}
                    onChange={(v) =>
                      handleChange('lead_status', v)
                    }
                  />

                  <SelectField
                    label="Lead Stage"
                    value={form.lead_stage}
                    options={leadStageOptions}
                    onChange={(v) =>
                      handleChange('lead_stage', v)
                    }
                  />
                </div>
              </div>
            </div>

            {/* FOLLOWUP */}
            <div className="bg-[#FFFDF8] border border-[#E7D3A4] rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <CalendarDays
                  size={18}
                  className="text-[#A9741F]"
                />

                <h3 className="font-semibold text-gray-800">
                  Follow-up Details
                </h3>
              </div>

                <div className="grid md:grid-cols-2 gap-4">

                <InputField
                  type="date"
                  label="Follow-up Date"
                  value={form.follow_up_date}
                  onChange={(v) =>
                    handleChange(
                      'follow_up_date',
                      v
                    )
                  }
                />

                <div />
              </div>

              <div className="mt-4">
                <label className="text-sm font-medium text-gray-700">
                  Remarks
                </label>

                <textarea
                  rows={4}
                  value={form.remarks}
                  onChange={(e) =>
                    handleChange(
                      'remarks',
                      e.target.value
                    )
                  }
                  className="mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 outline-none focus:border-[#B67D22]"
                  placeholder="Enter customer remarks..."
                />
              </div>
            </div>

            {/* ALERTS */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 text-sm">
                {error}
              </div>
            )}

            {success && (
              <div className="bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm flex items-center gap-2">
                <CheckCircle2 size={18} />
                {success}
              </div>
            )}

            {/* BUTTON */}
            <button
              type="submit"
              disabled={saving}
              className="bg-gradient-to-r from-[#8B5E12] via-[#B67D22] to-[#D4A437] hover:opacity-95 transition-all text-white font-semibold rounded-2xl px-8 py-3 flex items-center gap-2 shadow-lg"
            >
              {saving ? (
                <Loader2
                  size={18}
                  className="animate-spin"
                />
              ) : (
                <Save size={18} />
              )}

              {saving
                ? 'Saving Enquiry...'
                : 'Save Enquiry'}
            </button>
          </div>

          {/* RIGHT PANEL */}
          <div className="space-y-5 xl:max-w-[340px]">

            {/* SUMMARY */}
            <div className="sticky top-4 bg-[#FFF8E8] border border-[#E4C77F] rounded-2xl p-4 shadow-sm">
              <h3 className="font-bold text-base text-[#8B5E12] mb-3">
                Enquiry Summary
              </h3>

              <SummaryItem
                label="Customer"
                value={`${form.salutation} ${form.name}`.trim()}
              />

              <SummaryItem
                label="Mobile"
                value={form.mobile}
              />

              <SummaryItem
                label="Enquiry Type"
                value={form.enquiry_type}
              />

              <SummaryItem
                label="Ornament Type"
                value={form.ornament_type}
              />

              <SummaryItem
                label="Quantity"
                value={form.quantity}
              />

              <SummaryItem
                label="Gross Weight"
                value={form.gross_weight_gms}
              />

              <SummaryItem
                label="Net Weight"
                value={form.net_weight_gms}
              />

              <SummaryItem
                label="Rate"
                value={form.rate}
              />

              <SummaryItem
                label="Expected Rate"
                value={expectedRate}
              />

              {form.enquiry_type === 'Pledge Gold' && (
                <>
                  <SummaryItem
                    label="Pledge Amount"
                    value={form.pledge_amount}
                  />
                  <SummaryItem
                    label="Financier Name"
                    value={form.financier_name}
                  />
                  <SummaryItem
                    label="Financier Branch"
                    value={form.financier_branch}
                  />
                </>
              )}

              <SummaryItem
                label="Lead State"
                value={form.lead_state}
              />

              <SummaryItem
                label="Lead Status"
                value={form.lead_status}
              />

              <SummaryItem
                label="Lead Stage"
                value={form.lead_stage}
              />

              <SummaryItem
                label="Priority"
                value={form.priority}
              />
            </div>

            {/* RECENT */}
            <div className="bg-white border border-[#E5D2A0] rounded-2xl p-4 shadow-sm">
              <h3 className="font-bold text-gray-800 mb-4">
                Recent Enquiries
              </h3>

              {loadingRecent ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2
                    size={16}
                    className="animate-spin"
                  />
                  Loading...
                </div>
              ) : recentEnquiries.length > 0 ? (
                <div className="space-y-3">
                  {recentEnquiries.map(
                    (item) => (
                      <div
                        key={item.enquiry_id}
                        className="border border-[#E8D5A8] rounded-xl p-3 bg-[#FFFDF8]"
                      >
                        <div className="flex items-center justify-between">
                          <p className="font-semibold text-gray-800">
                            {
                              item.enquiry_type
                            }
                          </p>

                          <span className="text-xs text-[#A9741F] font-medium">
                            ID #
                            {
                              item.enquiry_id
                            }
                          </span>
                        </div>

                        <p className="text-sm text-gray-500 mt-1">
                          {item.created_at}
                        </p>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  No recent enquiries found
                </p>
              )}
            </div>

          </div>
        </form>
        </div>
      </div>
    </div>
  )
}

function InputField({
  label,
  value,
  onChange,
  type = 'text',
  readOnly = false
}) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700">
        {label}
      </label>

      <input
        type={type}
        value={value}
        readOnly={readOnly}
        onChange={(e) =>
          !readOnly && onChange(e.target.value)
        }
        className={`mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 outline-none focus:border-[#B67D22] ${
          readOnly ? 'bg-gray-100 text-gray-700 cursor-not-allowed' : ''
        }`}
      />
    </div>
  )
}

function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (ref.current && !ref.current.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const displayValue = value || placeholder || 'Select'

  return (
    <div className="relative" ref={ref}>
      <label className="text-sm font-medium text-gray-700">
        {label}
      </label>

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="mt-1 w-full rounded-xl border border-[#D8C08A] bg-white px-4 py-3 text-left outline-none focus:border-[#B67D22] flex items-center justify-between"
      >
        <span>{displayValue}</span>
        <span className="text-gray-400">▾</span>
      </button>

      {open && (
        <div className="absolute z-30 mt-2 w-full max-h-60 overflow-y-auto rounded-2xl border border-[#D8C08A] bg-white shadow-xl">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                onChange(option)
                setOpen(false)
              }}
              className="w-full text-left px-4 py-3 hover:bg-amber-50 focus:bg-amber-50"
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryItem({
  label,
  value
}) {
  return (
    <div className="mb-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">
        {label}
      </p>

      <p className="text-gray-900 font-semibold mt-1">
        {value || '—'}
      </p>
    </div>
  )
}

function formatDateTime(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
